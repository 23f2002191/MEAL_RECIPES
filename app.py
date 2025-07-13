from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import random
from rapidfuzz import process, fuzz

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
def home():
    import random

    meals = []
    all_items = {item.name.lower(): item for item in Item.query.all()}
    fully_matched_recipes = []

    for recipe in RAW_recipes:
        try:
            req = set(i.strip().lower() for i in recipe['ingredients'])
        except Exception as e:
            print(f"Skipping recipe due to parse error: {e}")
            continue

        available_items = []
        total_cost = total_cal = total_prot = 0
        has_discount = False

        for r in req:
            item = next((i for name, i in all_items.items() if r in name), None)
            if item:
                available_items.append(item)
                if item.discount and item.discount > 0:
                    has_discount = True
                total_cost += item.cost * (1 - (item.discount or 0) / 100)
                total_cal += item.calories or 0
                total_prot += item.protein or 0

        # ✅ Only include if all ingredients are available AND at least one has a discount
        if len(available_items) == len(req) and has_discount:
            fully_matched_recipes.append({
                'title': f"Recipe #{recipe['id']}",
                'ingredients': available_items,
                'cost': round(total_cost, 2),
                'calories': total_cal,
                'protein': total_prot
            })

    # ✅ Randomly select up to 12
    meals = random.sample(fully_matched_recipes, min(12, len(fully_matched_recipes)))

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
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/add-item', methods=['GET', 'POST'])
def add_item():
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        cost = float(request.form['cost'])
        calories = float(request.form['calories'])
        protein = float(request.form['protein'])
        discount = float(request.form.get('discount', 0))

        new_item = Item(name=name, cost=cost, calories=calories, protein=protein, discount=discount)
        db.session.add(new_item)
        db.session.commit()

        flash('Item added successfully!', 'success')
        return redirect(url_for('add_item'))

    # ✅ Fetch existing items to display
    all_items = Item.query.order_by(Item.name.asc()).all()
    return render_template('add_item.html', items=all_items)


@app.route('/add-meal', methods=['GET', 'POST'])
def add_meal():
    import json

    items = Item.query.all()
    all_items = {item.name.lower(): item for item in items}

    if request.method == 'POST':
        name = request.form['name']
        image_url = request.form.get('image_url', '')
        selected_item_ids = request.form.getlist('items')
        selected_items = Item.query.filter(Item.id.in_(selected_item_ids)).all()

        new_meal = Meal(name=name, image_url=image_url, items=selected_items)
        db.session.add(new_meal)
        db.session.commit()
        return redirect('/add-meal')

    with open('RAW_recipes.json') as f:
        raw_recipes = json.load(f)

    recipe_meals = []
    for r in raw_recipes:
        available = []
        unavailable = []
        for ing in r.get("ingredients", []):
            match = next((item for item_name, item in all_items.items() if ing.lower() in item_name), None)
            if match:
                available.append(match)
            else:
                unavailable.append(ing)

        recipe_meals.append({
            'id': r['id'],
            'name': f"Recipe {r['id']}",
            'image_url': "https://via.placeholder.com/300",
            'available': available,
            'unavailable': unavailable
        })

    # Sort by number of unavailable ingredients (ascending)
    recipe_meals.sort(key=lambda x: len(x['unavailable']))

    # Limit to top 30 recipes
    recipe_meals = recipe_meals[:30]

    return render_template('add_meal.html', items=items, meals=recipe_meals)

@app.route('/recipes', methods=['GET', 'POST'])
def recipe_matcher():
    matched = []

    def parse_float(val, default):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    if request.method == 'POST':
        user_input = [ing.strip().lower() for ing in request.form['ingredients'].split(',') if ing.strip()]
        min_price = parse_float(request.form.get('min_price'), 0)
        max_price = parse_float(request.form.get('max_price'), float('inf'))
        min_cal = parse_float(request.form.get('min_calories'), 0)
        max_cal = parse_float(request.form.get('max_calories'), float('inf'))
        min_prot = parse_float(request.form.get('min_protein'), 0)
        max_prot = parse_float(request.form.get('max_protein'), float('inf'))

        all_items = {item.name.lower(): item for item in Item.query.all()}
        item_names = list(all_items.keys())

        for recipe in RAW_recipes:
            try:
                recipe_ings = set(i.strip().lower() for i in recipe['ingredients'])
            except Exception as e:
                print(f"Skipping recipe due to parse error: {e}")
                continue

            # Fuzzy match: see how many user ingredients fuzzily match any in recipe_ings
            fuzzy_matches = set()
            for u_ing in user_input:
                match = process.extractOne(u_ing, recipe_ings, scorer=fuzz.partial_ratio, score_cutoff=75)
                if match:
                    fuzzy_matches.add(match[0])

            if not fuzzy_matches:
                continue  # skip if no match at all

            # Fetch item details from DB (fuzzy match again)
            available_items = []
            total_cost = total_cal = total_prot = 0
            for ing in recipe_ings:
                db_match = process.extractOne(ing, item_names, scorer=fuzz.partial_ratio, score_cutoff=75)
                if db_match:
                    item = all_items[db_match[0]]
                    available_items.append(item)
                    total_cost += item.cost * (1 - (item.discount or 0) / 100)
                    total_cal += item.calories or 0
                    total_prot += item.protein or 0

            unavailable = recipe_ings - {i.name.lower() for i in available_items}

            if min_price <= total_cost <= max_price and min_cal <= total_cal <= max_cal and min_prot <= total_prot <= max_prot:
                matched.append({
                    'title': f"Recipe #{recipe['id']}",
                    'instructions': '',
                    'available': available_items,
                    'unavailable': unavailable,
                    'cost': round(total_cost, 2),
                    'calories': round(total_cal, 2),
                    'protein': round(total_prot, 2),
                    'match_count': len(fuzzy_matches)
                })

        # Sort first by number of unavailable ingredients (ascending), then by match count (descending)
        matched = sorted(
            matched,
            key=lambda r: (len(r['unavailable']), -r['match_count'])
        )[:12]


    return render_template('recipes.html', matched=matched)





if __name__ == '__main__':
    app.run(debug=True)
