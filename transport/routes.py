import os
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import text
from werkzeug.utils import secure_filename

from extensions import db
from models.transport import Bus, Route, Stop, TransportAssignment
from models.teacher import Teacher

# ===============================
# 🔧 CONFIG
# ===============================
transport = Blueprint('transport', __name__, url_prefix='/transport')

UPLOAD_FOLDER = "static/uploads/bus_docs"

# ===============================
# 📁 FILE SAVE FUNCTION
# ===============================
def save_file(file):
    if file and file.filename != "":
        filename = secure_filename(file.filename)

        # folder ensure
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)

        return path
    return None


# ===============================
# 📊 DASHBOARD
# ===============================
@transport.route('/transport')
def dashboard():
    search = request.args.get('search', '')

    try:
        data = db.session.execute(text("""
            SELECT s.first_name,
                   b.bus_no,
                   b.driver_name,
                   r.route_name,
                   st.stop_name,
                   st.pickup_time
            FROM transport_assignments ta
            JOIN students s ON ta.student_id = s.id
            LEFT JOIN buses b ON ta.bus_id = b.id
            LEFT JOIN routes r ON ta.route_id = r.id
            LEFT JOIN stops st ON ta.stop_id = st.id
            WHERE s.first_name LIKE :q
               OR b.bus_no LIKE :q
               OR b.driver_name LIKE :q
        """), {"q": f"%{search}%"}).fetchall()

    except Exception as e:
        print("🚨 Transport Error:", e)
        data = []

    return render_template("transport/dashboard.html", data=data)


# ===============================
# 🚌 ADD BUS
# ===============================
@transport.route('/bus/add', methods=['GET', 'POST'])
def add_bus():

    drivers = Teacher.query.filter_by(
        school_id=current_user.school_id,
        designation="Driver"
    ).all()
    if request.method == 'POST':

        def parse_date(val):
            return datetime.strptime(val, "%Y-%m-%d").date() if val else None

        bus = Bus(
            school_id=current_user.school_id,

            # 📋 BASIC
            bus_no=request.form.get('bus_no'),
            registration_no=request.form.get('registration_no'),
            chassis_no=request.form.get('chassis_no'),
            engine_no=request.form.get('engine_no'),
            model=request.form.get('model'),
            bus_type=request.form.get('bus_type'),

            # 💺 CAPACITY
            capacity=request.form.get('capacity'),
            max_students=request.form.get('max_students'),

            # 👨‍✈️ STAFF
            driver_name=request.form.get('driver_name'),
            driver_mobile=request.form.get('driver_mobile'),
            helper_name=request.form.get('helper_name'),

            # 🛠️ MAINTENANCE
            last_service=parse_date(request.form.get('last_service')),
            next_service=parse_date(request.form.get('next_service')),
            gps_id=request.form.get('gps_id'),
            cctv=request.form.get('cctv'),

            # 🚦 STATUS
            status=request.form.get('status'),

            # 📄 DOCUMENTS
            rc_book=save_file(request.files.get('rc_book')),
            insurance=save_file(request.files.get('insurance')),
            insurance_expiry=parse_date(request.form.get('insurance_expiry')),
            puc=save_file(request.files.get('puc')),
            puc_expiry=parse_date(request.form.get('puc_expiry')),
            fitness=save_file(request.files.get('fitness')),
            fitness_expiry=parse_date(request.form.get('fitness_expiry'))
        )

        db.session.add(bus)
        db.session.commit()

        flash("Bus Added Successfully", "success")
        return redirect(url_for('transport.bus_list'))

    return render_template('transport/add_bus.html',drivers=drivers)


# ===============================
# 📋 BUS LIST
# ===============================
@transport.route('/bus/list')
def bus_list():
    buses = Bus.query.filter_by(
        school_id=current_user.school_id
    ).all()

    return render_template('transport/bus_list.html', buses=buses)

@transport.route('/bus/edit/<int:id>', methods=['GET', 'POST'])
def edit_bus(id):
    bus = Bus.query.get_or_404(id)
    drivers = Teacher.query.filter_by(
    school_id=current_user.school_id,
    designation="Driver"
    ).all()

    if request.method == 'POST':

        def parse_date(val):
            from datetime import datetime
            return datetime.strptime(val, "%Y-%m-%d").date() if val else None

        # Basic
        bus.bus_no = request.form.get('bus_no')
        bus.registration_no = request.form.get('registration_no')
        bus.chassis_no = request.form.get('chassis_no')
        bus.engine_no = request.form.get('engine_no')
        bus.model = request.form.get('model')
        bus.bus_type = request.form.get('bus_type')

        # Capacity
        bus.capacity = request.form.get('capacity')
        bus.max_students = request.form.get('max_students')

        # Staff
        bus.driver_name = request.form.get('driver_name')
        bus.driver_mobile = request.form.get('driver_mobile')
        bus.helper_name = request.form.get('helper_name')

        # Maintenance
        bus.last_service = parse_date(request.form.get('last_service'))
        bus.next_service = parse_date(request.form.get('next_service'))
        bus.gps_id = request.form.get('gps_id')
        bus.cctv = request.form.get('cctv')

        # Status
        bus.status = request.form.get('status')

        # Documents (update if new upload)
        file = request.files.get('rc_book')
        if file:
            bus.rc_book = save_file(file)

        file = request.files.get('insurance')
        if file:
            bus.insurance = save_file(file)

        bus.insurance_expiry = parse_date(request.form.get('insurance_expiry'))

        file = request.files.get('puc')
        if file:
            bus.puc = save_file(file)

        bus.puc_expiry = parse_date(request.form.get('puc_expiry'))

        file = request.files.get('fitness')
        if file:
            bus.fitness = save_file(file)

        bus.fitness_expiry = parse_date(request.form.get('fitness_expiry'))

        db.session.commit()

        flash("Bus Updated Successfully", "success")
        return redirect(url_for('transport.bus_list'))

    return render_template('transport/edit_bus.html', bus=bus,drivers=drivers)

@transport.route('/bus/view/<int:id>')
def view_bus(id):
    bus = Bus.query.get_or_404(id)
    return render_template('transport/view_bus.html', bus=bus)

@transport.route('/bus/delete/<int:id>', methods=['POST'])
def delete_bus(id):
    bus = Bus.query.get_or_404(id)

    db.session.delete(bus)
    db.session.commit()

    flash("Bus Deleted Successfully", "danger")
    return redirect(url_for('transport.bus_list'))

# =======================
# 🗺️ ADD ROUTE (ADVANCED)
# =======================
@transport.route('/route/add', methods=['GET', 'POST'])
def add_route():

    buses = Bus.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST':
        route = Route(
            school_id=current_user.school_id,

            # BASIC
            route_name=request.form.get('route_name'),
            route_code=request.form.get('route_code'),
            start_point=request.form.get('start_point'),
            end_point=request.form.get('end_point'),
            distance_km=request.form.get('distance_km'),

            # BUS
            bus_id=request.form.get('bus_id'),
            backup_bus_id=request.form.get('backup_bus_id'),

            # DRIVER
            driver_name=request.form.get('driver_name'),
            driver_mobile=request.form.get('driver_mobile'),

            # FEE
            fare_type=request.form.get('fare_type'),
            base_fare=request.form.get('base_fare'),

            # TRACKING
            gps_enabled=True if request.form.get('gps_enabled') else False,
            geofence_enabled=True if request.form.get('geofence_enabled') else False
        )

        db.session.add(route)
        db.session.commit()

        flash("Route Added", "success")
        return redirect(url_for('transport.route_list'))

    return render_template('transport/add_route.html', buses=buses)

# =======================
# 📋 ROUTE LIST
# =======================
@transport.route('/route/list')
def route_list():
    routes = Route.query.filter_by(
        school_id=current_user.school_id
    ).all()

    return render_template('transport/route_list.html', routes=routes)

@transport.route('/route/edit/<int:id>', methods=['GET', 'POST'])
def edit_route(id):

    route = Route.query.get_or_404(id)
    buses = Bus.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST':

        route.route_name = request.form.get('route_name')
        route.route_code = request.form.get('route_code')
        route.start_point = request.form.get('start_point')
        route.end_point = request.form.get('end_point')
        route.distance_km = request.form.get('distance_km')

        route.bus_id = request.form.get('bus_id')
        route.backup_bus_id = request.form.get('backup_bus_id')

        route.driver_name = request.form.get('driver_name')
        route.driver_mobile = request.form.get('driver_mobile')

        route.fare_type = request.form.get('fare_type')
        route.base_fare = request.form.get('base_fare')

        route.gps_enabled = True if request.form.get('gps_enabled') else False
        route.geofence_enabled = True if request.form.get('geofence_enabled') else False

        db.session.commit()

        flash("Route Updated Successfully", "success")
        return redirect(url_for('transport.route_list'))

    return render_template(
        'transport/edit_route.html',
        route=route,
        buses=buses
    )

# =======================
# 📍 ADD STOP
# =======================
@transport.route('/stop/add', methods=['GET', 'POST'])
def add_stop():

    routes = Route.query.filter_by(
        school_id=current_user.school_id
    ).all()

    if request.method == 'POST':
        stop = Stop(
            route_id=request.form.get('route_id'),
            stop_name=request.form.get('stop_name'),
            pickup_time=request.form.get('pickup_time'),

            # NEW
            sequence=request.form.get('sequence'),
            distance_km=request.form.get('distance_km'),
            fare=request.form.get('fare')
        )

        db.session.add(stop)
        db.session.commit()

        flash("Stop Added", "success")
        return redirect(url_for('transport.add_stop'))

    return render_template('transport/add_stop.html', routes=routes)


@transport.route('/stop/edit/<int:id>', methods=['GET', 'POST'])
def edit_stop(id):

    stop = Stop.query.get_or_404(id)
    routes = Route.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST':

        stop.route_id = request.form.get('route_id')
        stop.stop_name = request.form.get('stop_name')
        stop.pickup_time = request.form.get('pickup_time')
        stop.sequence = request.form.get('sequence')
        stop.distance_km = request.form.get('distance_km')
        stop.fare = request.form.get('fare')

        db.session.commit()

        flash("Stop Updated Successfully", "success")
        return redirect(url_for('transport.route_detail', id=stop.route_id))

    return render_template(
        'transport/edit_stop.html',
        stop=stop,
        routes=routes
    )

@transport.route('/stop/<int:id>')
def view_stop(id):

    stop = Stop.query.get_or_404(id)

    return render_template(
        'transport/view_stop.html',
        stop=stop
    )

@transport.route('/stop/delete/<int:id>')
def delete_stop(id):

    stop = Stop.query.get_or_404(id)
    route_id = stop.route_id

    Stop.query.filter_by(id=id).delete()
    db.session.commit()

    flash("Stop Deleted Successfully", "danger")
    return redirect(url_for('transport.route_detail', id=route_id))

@transport.route('/stop/list')
def stop_list():

    stops = Stop.query.join(Route).filter(
        Route.school_id == current_user.school_id
    ).order_by(Stop.sequence).all()

    return render_template(
        'transport/stop_list.html',
        stops=stops
    )  
# =======================
# 🔍 ROUTE DETAIL
# =======================
@transport.route('/route/<int:id>')
def route_detail(id):

    route = Route.query.get_or_404(id)

    stops = Stop.query.filter_by(route_id=id).order_by(Stop.sequence).all()

    students = TransportAssignment.query.filter_by(
        route_id=id,
        school_id=current_user.school_id
    ).all()

    return render_template(
        'transport/route_detail.html',
        route=route,
        stops=stops,
        students=students
    )
from flask import jsonify


@transport.route('/route/delete/<int:id>')
def delete_route(id):

    route = Route.query.get_or_404(id)

    # 🔥 DELETE ALL STOPS
    Stop.query.filter_by(route_id=id).delete()

    # 🔥 DELETE ALL ASSIGNMENTS
    TransportAssignment.query.filter_by(route_id=id).delete()

    # 🔥 DELETE ROUTE
    db.session.delete(route)
    db.session.commit()

    flash("Route Deleted Successfully", "danger")
    return redirect(url_for('transport.route_list'))

@transport.route('/get-stops/<int:route_id>')
def get_stops(route_id):
    stops = Stop.query.filter_by(route_id=route_id).all()

    return jsonify([
        {
            "id": s.id,
            "stop_name": s.stop_name
        }
        for s in stops
    ])

