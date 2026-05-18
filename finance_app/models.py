from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.Date, default=date.today)

    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f'<User {self.email}>'


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type     = db.Column(db.String(10), nullable=False)   # 'income' | 'expense'
    category = db.Column(db.String(100), nullable=False)
    amount   = db.Column(db.Float, nullable=False)
    note     = db.Column(db.String(300), default='')
    date     = db.Column(db.Date, default=date.today, nullable=False)

    def __repr__(self):
        return f'<Transaction {self.type} {self.amount}>'

    @property
    def amount_fmt(self):
        return f'{self.amount:,.2f}'

    @property
    def type_label(self):
        return 'Доход' if self.type == 'income' else 'Расход'
