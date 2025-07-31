from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from flask import request, jsonify

app = Flask(__name__, static_url_path='/decal/static')
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///decal.db'
app.config['APPLICATION_ROOT'] = '/decal'


db = SQLAlchemy(app)


logging.basicConfig(filename='tissuelog.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# User model: stores username, password, role ('pathologist' or 'MTA')
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)

# TissueProcessing: stores processing entries
class TissueProcessing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(50), db.ForeignKey('user.username'))
    case_id = db.Column(db.String(50))
    tissue_id = db.Column(db.String(50))
    process = db.Column(db.String(10))
    timestamp = db.Column(db.DateTime, default=datetime.now(ZoneInfo("Europe/Berlin")))

# TissueStatus: stores current status
class TissueStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    u_processid = db.Column(db.Integer, db.ForeignKey('tissue_processing.id'))
    tissue_id = db.Column(db.String(50))
    user_name = db.Column(db.String(50), db.ForeignKey('user.username'))
    case_id = db.Column(db.String(50))
    process = db.Column(db.String(10))
    status = db.Column(db.String(20), default='Pending')  # 'Pending', 'Checked', 'Done'
    init_date = db.Column(db.DateTime, default=datetime.now(ZoneInfo("Europe/Berlin")))
    last_updated = db.Column(db.DateTime, default=datetime.now(ZoneInfo("Europe/Berlin")))
    mta_name = db.Column(db.String(50))

# TissueHistory: stores history logs
class TissueHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    u_processid = db.Column(db.Integer, db.ForeignKey('tissue_processing.id'))
    tissue_id = db.Column(db.String(50))
    case_id = db.Column(db.String(50))
    process = db.Column(db.String(20))
    action = db.Column(db.String(30))  # 'Checked' or 'Done'
    timestamp = db.Column(db.DateTime, default=datetime.now(ZoneInfo("Europe/Berlin")))
    mta_name = db.Column(db.String(50))


@app.route('/decal/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['username'] = user.username
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/decal/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/decal/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    role = session['role']
    if role == 'pathologist':
        return redirect(url_for('pathologist_view'))
    elif role == 'MTA':
        return redirect(url_for('mta_view'))
    elif role == 'LAB':
        return redirect(url_for('lab_view'))
    return "Unauthorized"


@app.route('/decal/pathologist', methods=['GET', 'POST'])
def pathologist_view():
    if 'username' not in session or session['role'] != 'pathologist':
        return redirect(url_for('login'))

    result = None

    if request.method == 'POST':
        try:
            case_id = request.form['case_id']
            tissue_id = request.form['tissue_id']
            process = request.form['process']
            user_name = session['username']
            current_time = datetime.now(ZoneInfo("Europe/Berlin"))

            # Immer neuen TissueProcessing Eintrag anlegen
            new_entry = TissueProcessing(
                user_name=user_name,
                case_id=case_id,
                tissue_id=tissue_id,
                process=process,
                timestamp=current_time
            )
            db.session.add(new_entry)
            db.session.flush()  # Flush to assign `new_entry.id`

            processing_id = new_entry.id

            new_status = TissueStatus(
                u_processid=processing_id,
                tissue_id=tissue_id,
                case_id=case_id,
                user_name=user_name,
                process=process,
                status='Pending',
                last_updated=current_time,
                init_date=current_time,
                mta_name=''
            )
            db.session.add(new_status)

            # Step 3: Use processing_id in TissueHistory
            new_history = TissueHistory(
                u_processid=processing_id,
                tissue_id=tissue_id,
                case_id=case_id,
                process=process,
                action='Init',
                timestamp=current_time,
                mta_name=session['username']
            )
            db.session.add(new_history)

            db.session.commit()

            result = 'success'

            log_message = f"Case ID: {case_id}, Tissue ID: {tissue_id}, Process: {process}, Username: {user_name}, Zeitpunkt: {current_time} gespeichert."
            logging.info(log_message)

        except Exception as e:
            db.session.rollback()
            log_message = f"Case ID: {case_id}, Tissue ID: {tissue_id}, Process: {process}, Username: {user_name}, Zeitpunkt: {current_time} nicht gespeichert."
            logging.error(f"Fehler beim Speichern: {e}")
            logging.error(log_message)
            result = 'fail'
    return render_template('pathologist.html', result=result)


@app.route('/decal/mta')
def mta_view():
    if 'username' not in session or session['role'] != 'MTA':
        return redirect(url_for('login'))
    tissues = TissueStatus.query.filter(TissueStatus.status != 'Done').all()
    return render_template('mta.html', tissues=tissues)


@app.route('/decal/lab')
def lab_view():
    if 'username' not in session or session['role'] != 'LAB':
        return redirect(url_for('login'))
    tissues = TissueStatus.query.all()
    return render_template('lab.html', tissues=tissues)


@app.route('/decal/update_tissue', methods=['POST'])
def update_tissue():
    if 'username' not in session or session['role'] != 'MTA':
        return jsonify({'error':'Unauthorized'}), 403
    data = request.json
    utissue_id = data['tissue_id']
    action = data['action']  # 'checked' or 'done'
    haction = "DONE"
    tissue = TissueStatus.query.filter_by(u_processid=utissue_id).first()
    if tissue:
        if action == 'checked':
            tissue.status = 'Checked'
            haction = 'Checked'
        elif action == 'done':
            tissue.status = 'Done'
            haction = 'Done'
        elif action == 'acid':
            tissue.status = 'Changed to ACID'            
            tissue.process = 'ACID'
            haction = 'Changed to ACID'
        tissue.last_updated = datetime.now(ZoneInfo("Europe/Berlin"))
        tissue.mta_name = session['username']

        # Log to history
        log = TissueHistory(
            tissue_id=tissue.tissue_id,
            u_processid=utissue_id,
            case_id=tissue.case_id,
            process=tissue.process,
            timestamp=tissue.last_updated,
            action=haction,
            mta_name=session['username']
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({'status':'success'})
    return jsonify({'error':'Tissue not found'}), 404

@app.route('/decal/tissue/<id>')
def tissue_detail(id):
    tissue = TissueStatus.query.filter_by(u_processid=id).first()
    history = TissueHistory.query.filter_by(u_processid=id).order_by(TissueHistory.timestamp.desc()).all()
    return render_template('tissue_history.html', tissue=tissue, history=history)


@app.before_request
def create_tables():
    db.create_all()
    # Create default users if not exist
    if not User.query.filter_by(username='pa').first():
        db.session.add(User(username='pa', password='pa', role='pathologist'))

    if not User.query.filter_by(username='mta').first():
        db.session.add(User(username='mta', password='mta', role='MTA'))

    if not User.query.filter_by(username='lab').first():
        db.session.add(User(username='lab', password='lab', role='LAB'))
    db.session.commit()

if __name__ == '__main__':
    app.run()
