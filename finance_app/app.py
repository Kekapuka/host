from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Transaction
from datetime import datetime, date
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'finance-app-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Войдите в систему для доступа к этой странице.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()


# ── ГЛАВНАЯ ──
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


# ── РЕГИСТРАЦИЯ ──
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        if not all([name, email, password, confirm]):
            flash('Заполните все поля.', 'error')
        elif password != confirm:
            flash('Пароли не совпадают.', 'error')
        elif len(password) < 6:
            flash('Пароль должен содержать не менее 6 символов.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует.', 'error')
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f'Добро пожаловать, {name}!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('register.html')


# ── ВХОД ──
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Неверный email или пароль.', 'error')
    return render_template('login.html')


# ── ВЫХОД ──
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ── ДОБАВИТЬ ОПЕРАЦИЮ ──
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        t_type    = request.form.get('type')
        category  = request.form.get('category', '').strip()
        amount    = request.form.get('amount', '0')
        note      = request.form.get('note', '').strip()
        date_str  = request.form.get('date')

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash('Введите корректную сумму.', 'error')
            return render_template('add_transaction.html')

        try:
            t_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        except ValueError:
            t_date = date.today()

        tx = Transaction(
            user_id=current_user.id,
            type=t_type,
            category=category,
            amount=amount,
            note=note,
            date=t_date,
        )
        db.session.add(tx)
        db.session.commit()
        flash('Операция добавлена!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_transaction.html', today=date.today().isoformat())


# ── УДАЛИТЬ ОПЕРАЦИЮ ──
@app.route('/delete/<int:tx_id>', methods=['POST'])
@login_required
def delete_transaction(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    db.session.delete(tx)
    db.session.commit()
    flash('Операция удалена.', 'success')
    return redirect(url_for('history'))


# ── ИСТОРИЯ ──
@app.route('/history')
@login_required
def history():
    q     = Transaction.query.filter_by(user_id=current_user.id)
    ftype = request.args.get('type', '')
    fcat  = request.args.get('category', '')
    if ftype in ('income', 'expense'):
        q = q.filter_by(type=ftype)
    if fcat:
        q = q.filter_by(category=fcat)
    transactions = q.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    categories = sorted({t.category for t in Transaction.query.filter_by(user_id=current_user.id).all() if t.category})
    return render_template('history.html', transactions=transactions, categories=categories, ftype=ftype, fcat=fcat)


# ── ДАШБОРД ──
@app.route('/dashboard')
@login_required
def dashboard():
    all_tx = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.date.desc()).all()

    total_income  = sum(t.amount for t in all_tx if t.type == 'income')
    total_expense = sum(t.amount for t in all_tx if t.type == 'expense')
    balance       = total_income - total_expense

    # Расходы по категориям
    expense_by_cat = {}
    for t in all_tx:
        if t.type == 'expense':
            expense_by_cat[t.category] = expense_by_cat.get(t.category, 0) + t.amount

    # Доходы по категориям
    income_by_cat = {}
    for t in all_tx:
        if t.type == 'income':
            income_by_cat[t.category] = income_by_cat.get(t.category, 0) + t.amount

    # По месяцам (последние 6)
    monthly = {}
    for t in all_tx:
        key = t.date.strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'income': 0, 'expense': 0}
        monthly[key][t.type] += t.amount

    months_sorted = sorted(monthly.keys())[-6:]
    chart_months   = [m[5:] + '.' + m[:4] for m in months_sorted]
    chart_income   = [round(monthly[m]['income'], 2)  for m in months_sorted]
    chart_expense  = [round(monthly[m]['expense'], 2) for m in months_sorted]

    recent = all_tx[:8]

    return render_template('dashboard.html',
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        expense_by_cat=expense_by_cat,
        income_by_cat=income_by_cat,
        chart_months=json.dumps(chart_months),
        chart_income=json.dumps(chart_income),
        chart_expense=json.dumps(chart_expense),
        recent=recent,
    )


if __name__ == '__main__':
    app.run(debug=True)
