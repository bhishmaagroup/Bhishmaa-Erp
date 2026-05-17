from extensions import db


# 🚌 BUS (NO CHANGE ❌)
class Bus(db.Model):
    __tablename__ = "buses"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)

    # 📋 Basic
    bus_no = db.Column(db.String(50))
    registration_no = db.Column(db.String(100))
    chassis_no = db.Column(db.String(100))
    engine_no = db.Column(db.String(100))
    model = db.Column(db.String(100))
    bus_type = db.Column(db.String(50))

    # 💺 Capacity
    capacity = db.Column(db.Integer)
    max_students = db.Column(db.Integer)

    # 👨‍✈️ Staff
    driver_name = db.Column(db.String(100))
    driver_mobile = db.Column(db.String(20))
    helper_name = db.Column(db.String(100))

    # 🛠️ Maintenance
    last_service = db.Column(db.Date)
    next_service = db.Column(db.Date)
    gps_id = db.Column(db.String(100))
    cctv = db.Column(db.String(50))

    # 🚦 Status
    status = db.Column(db.String(50))

    # 📄 Documents
    rc_book = db.Column(db.String(200))
    insurance = db.Column(db.String(200))
    insurance_expiry = db.Column(db.Date)
    puc = db.Column(db.String(200))
    puc_expiry = db.Column(db.Date)
    fitness = db.Column(db.String(200))
    fitness_expiry = db.Column(db.Date)

    # 🔗 Relationships
    routes = db.relationship('Route', backref='bus', lazy=True)


# 🗺️ ROUTE (🔥 ONLY ADDITIONS)
class Route(db.Model):
    __tablename__ = "routes"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)

    route_name = db.Column(db.String(100))

    # 🔗 Bus Link
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'))

    # =========================
    # 🔥 NEW IMPORTANT FIELDS
    # =========================
    route_code = db.Column(db.String(50))
    start_point = db.Column(db.String(150))
    end_point = db.Column(db.String(150))
    distance_km = db.Column(db.Float)

    backup_bus_id = db.Column(db.Integer)
    driver_name = db.Column(db.String(100))
    driver_mobile = db.Column(db.String(20))

    fare_type = db.Column(db.String(50))   # one-way / two-way
    base_fare = db.Column(db.Float)

    gps_enabled = db.Column(db.Boolean, default=False)
    geofence_enabled = db.Column(db.Boolean, default=False)

    # 🔗 Relationships
    stops = db.relationship('Stop', backref='route', lazy=True)


# 📍 STOP (🔥 SMALL UPGRADE)
class Stop(db.Model):
    __tablename__ = "stops"

    id = db.Column(db.Integer, primary_key=True)

    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'))
    stop_name = db.Column(db.String(100))
    pickup_time = db.Column(db.String(20))

    # 🔥 NEW
    sequence = db.Column(db.Integer)      # stop order
    distance_km = db.Column(db.Float)     # distance from school
    fare = db.Column(db.Float)            # stop-wise fee


# 👨‍🎓 TRANSPORT ASSIGNMENT (NO CHANGE ❌)
class TransportAssignment(db.Model):
    __tablename__ = "transport_assignments"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, nullable=False)

    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'))
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'))
    stop_id = db.Column(db.Integer, db.ForeignKey('stops.id'))

    # 🔗 Relationships
    bus = db.relationship('Bus')
    route = db.relationship('Route')
    stop = db.relationship('Stop')