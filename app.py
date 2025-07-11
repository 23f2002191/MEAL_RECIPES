from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json

# Setup
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, 'RAW_recipes.json')

with open(file_path, 'r') as f:
    RAW_recipes = json.load(f)

app = Flask(__name__)
app.secret_key = 'secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///grocery.db'
db = SQLAlchemy(app)

# Meal-Item relationship
meal_items = db.Table('meal_items',
    db.Column('meal_id', db.Integer, db.ForeignKey('meal.id')),
    db.Column('item_id', db.Integer, db.ForeignKey('item.id'))
)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(300))
    calories = db.Column(db.Float, default=0)
    protein = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)

class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(300))
    items = db.relationship('Item', secondary=meal_items, backref='meals')

    @property
    def total_cost(self):
        return sum(item.cost for item in self.items)

    @property
    def total_calories(self):
        return sum(item.calories for item in self.items)

    @property
    def total_protein(self):
        return sum(item.protein for item in self.items)

# Create DB and default admin
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password=generate_password_hash('admin'), is_admin=True))
        db.session.commit()

# Routes
@app.route('/')
def index():
    meals = Meal.query.all()
    return render_template('index.html', meals=meals)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user'] = user.username
            session['is_admin'] = user.is_admin
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/add-item', methods=['GET', 'POST'])
def add_item():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        cost = float(request.form['cost'])
        image_url = request.form['image_url']
        calories = float(request.form.get('calories', 0))
        protein = float(request.form.get('protein', 0))
        discount = float(request.form.get('discount', 0))
        item = Item(name=name, cost=cost, image_url=image_url, calories=calories, protein=protein, discount=discount)
        db.session.add(item)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_item.html')

@app.route('/add-meal', methods=['GET', 'POST'])
def add_meal():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    items = Item.query.all()
    if request.method == 'POST':
        name = request.form['name']
        image_url = request.form['image_url']
        selected_ids = request.form.getlist('items')
        selected_items = Item.query.filter(Item.id.in_(selected_ids)).all()
        meal = Meal(name=name, image_url=image_url, items=selected_items)
        db.session.add(meal)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_meal.html', items=items)

@app.route('/recipes', methods=['GET', 'POST'])
def recipe_matcher():
    matched = []

    def parse_float(val, default):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    if request.method == 'POST':
        user_ing = set(ing.strip().lower() for ing in request.form['ingredients'].split(','))

        min_price = parse_float(request.form.get('min_price'), 0)
        max_price = parse_float(request.form.get('max_price'), float('inf'))
        min_cal = parse_float(request.form.get('min_calories'), 0)
        max_cal = parse_float(request.form.get('max_calories'), float('inf'))
        min_prot = parse_float(request.form.get('min_protein'), 0)
        max_prot = parse_float(request.form.get('max_protein'), float('inf'))

        for recipe in RAW_recipes:
            try:
                req = set(i.strip().lower() for i in recipe['ingredients'])
            except Exception as e:
                print(f"Skipping recipe due to parse error: {e}")
                continue

            matched_ing = user_ing & req
            if not matched_ing:
                continue

            available_items = []
            total_cost = total_cal = total_prot = 0
            for r in req:
                item = Item.query.filter(Item.name.ilike(f"%{r}%")).first()
                if item:
                    available_items.append(item)
                    total_cost += item.cost * (1 - (item.discount or 0) / 100)
                    total_cal += item.calories or 0
                    total_prot += item.protein or 0

            unavailable = req - {i.name.lower() for i in available_items}

            if min_price <= total_cost <= max_price and min_cal <= total_cal <= max_cal and min_prot <= total_prot <= max_prot:
                matched.append({
                    'title': f"Recipe #{recipe['id']}",
                    'instructions': '',
                    'available': available_items,
                    'unavailable': unavailable,
                    'cost': round(total_cost, 2),
                    'calories': round(total_cal, 2),
                    'protein': round(total_prot, 2),
                    'match_count': len(matched_ing)
                })

        # Sort by number of matching ingredients (descending), then take top 10
        matched = sorted(matched, key=lambda r: r['match_count'], reverse=True)[:10]

    return render_template('recipes.html', matched=matched)




if __name__ == '__main__':
    app.run(debug=True)
