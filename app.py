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
    from datetime import datetime
    from flask import session

    now = datetime.utcnow()

    if 'last_update_time' not in session:
        session['last_update_time'] = now.isoformat()

    last_update_time = datetime.fromisoformat(session['last_update_time'])
    seconds_ago = int((now - last_update_time).total_seconds())



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

        if len(available_items) == len(req) and has_discount:
            original_cost = sum(item.cost for item in available_items)
            discounted_cost = sum(item.cost * (1 - (item.discount or 0) / 100) for item in available_items)
            savings = original_cost - discounted_cost

            fully_matched_recipes.append({
                'id': recipe['id'],
                'title': f"Recipe #{recipe['id']}",
                'ingredients': available_items,
                'cost': round(discounted_cost, 2),
                'original_cost': round(original_cost, 2),
                'savings': round(savings, 2),
                'calories': total_cal,
                'protein': total_prot
            })


    meals = random.sample(fully_matched_recipes, min(12, len(fully_matched_recipes)))

    return render_template('index.html', meals=meals, is_admin=session.get('is_admin'), updated_ago=seconds_ago, now=now)


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
        user_ing = set(i.strip().lower() for i in request.form['ingredients'].split(','))
        min_price = parse_float(request.form.get('min_price'), 0)
        max_price = parse_float(request.form.get('max_price'), float('inf'))
        min_cal = parse_float(request.form.get('min_calories'), 0)
        max_cal = parse_float(request.form.get('max_calories'), float('inf'))
        min_prot = parse_float(request.form.get('min_protein'), 0)
        max_prot = parse_float(request.form.get('max_protein'), float('inf'))

        all_items = {item.name.lower(): item for item in Item.query.all()}

        for recipe in RAW_recipes:
            ingredients = set(i.lower() for i in recipe.get("ingredients", []))
            matched_ing = user_ing & ingredients
            if not matched_ing:
                continue

            available, unavailable = [], []
            total_cost = total_cal = total_prot = 0

            for ing in ingredients:
                item = next((itm for name, itm in all_items.items() if ing in name), None)
                if item:
                    available.append(item)
                    total_cost += item.cost * (1 - (item.discount or 0) / 100)
                    total_cal += item.calories or 0
                    total_prot += item.protein or 0
                else:
                    unavailable.append(ing)

            if min_price <= total_cost <= max_price and min_cal <= total_cal <= max_cal and min_prot <= total_prot <= max_prot:
                matched.append({
                    'id': recipe['id'],  # needed for Add to Cart
                    'title': f"Recipe #{recipe['id']}",
                    'available': available,
                    'unavailable': unavailable,
                    'cost': round(total_cost, 2),
                    'calories': round(total_cal, 2),
                    'protein': round(total_prot, 2),
                    'match_count': len(matched_ing)
                })

        matched = sorted(matched, key=lambda r: (len(r['unavailable']), -r['match_count']))[:12]

    return render_template('recipes.html', matched=matched)


@app.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))

    import json
    from collections import Counter
    from datetime import datetime

    all_items = {item.name.lower(): item for item in Item.query.all()}
    total_items = len(all_items)
    discounted_items = [item for item in all_items.values() if item.discount > 0]
    avg_discount = round(sum(i.discount for i in discounted_items) / total_items, 2) if total_items else 0

    with open('RAW_recipes.json') as f:
        recipes = json.load(f)

    total_meals = len(recipes)
    fully_available_discounted_meals = 0
    one_missing = 0
    many_missing = 0

    missing_counter = Counter()

    for recipe in recipes:
        try:
            ingredients = set(i.strip().lower() for i in recipe.get("ingredients", []))
        except Exception:
            continue

        available_count = 0
        has_discount = False

        for ing in ingredients:
            matched_item = next((item for name, item in all_items.items() if ing in name), None)
            if matched_item:
                available_count += 1
                if matched_item.discount > 0:
                    has_discount = True
            else:
                missing_counter[ing] += 1

        missing_count = len(ingredients) - available_count

        if missing_count == 0 and has_discount:
            fully_available_discounted_meals += 1
        elif missing_count == 1:
            one_missing += 1
        elif missing_count >= 2:
            many_missing += 1

    most_missing = missing_counter.most_common(5)
    last_updated = session.get('last_update_time', datetime.utcnow().isoformat())

    return render_template('admin_dashboard.html', **{
        'total_items': total_items,
        'discounted_items': len(discounted_items),
        'avg_discount': avg_discount,
        'discount_10_plus': len([i for i in discounted_items if i.discount >= 10]),
        'discount_20_plus': len([i for i in discounted_items if i.discount >= 20]),
        'total_meals': total_meals,
        'fully_available_discounted_meals': fully_available_discounted_meals,
        'one_missing': one_missing,
        'many_missing': many_missing,
        'most_missing': most_missing,
        'last_updated': last_updated
    })

@app.route('/add-to-cart/<int:meal_id>', methods=['POST'])
def add_to_cart(meal_id):
    if 'cart' not in session:
        session['cart'] = []

    cart = session['cart']
    
    # Ensure it's a list of dicts and not a list of lists
    for item in cart:
        if isinstance(item, dict) and item.get('meal_id') == meal_id:
            item['qty'] += 1
            break
    else:
        cart.append({'meal_id': meal_id, 'qty': 1})
    
    session['cart'] = cart
    return redirect('/')


@app.route('/cart')
def view_cart():
    from flask import session
    cart = session.get('cart', [])
    cart_items = []
    total_cost = total_calories = total_protein = total_savings = 0

    all_items = {item.name.lower(): item for item in Item.query.all()}
    
    for entry in cart:
        meal_id = entry['meal_id']
        qty = entry['qty']

        # Find the corresponding recipe
        recipe = next((r for r in RAW_recipes if r['id'] == meal_id), None)
        if not recipe:
            continue

        available_items = []
        cost = cal = prot = original = 0

        for ing in recipe['ingredients']:
            item = next((i for name, i in all_items.items() if ing.lower() in name), None)
            if item:
                available_items.append(item)
                original += item.cost
                cost += item.cost * (1 - (item.discount or 0) / 100)
                cal += item.calories or 0
                prot += item.protein or 0

        total_cost += cost * qty
        total_calories += cal * qty
        total_protein += prot * qty
        total_savings += (original - cost) * qty

        cart_items.append({
            'title': f"Recipe #{meal_id}",
            'ingredients': available_items,
            'cost': round(cost * qty, 2),
            'calories': round(cal * qty),
            'protein': round(prot * qty),
            'qty': qty
        })

    return render_template('cart.html',
        cart_items=cart_items,
        total_cost=round(total_cost, 2),
        total_calories=round(total_calories),
        total_protein=round(total_protein),
        total_savings=round(total_savings, 2)
    )


@app.route('/checkout', methods=['POST'])
def checkout():
    session['cart'] = []
    return redirect(url_for('home'))



if __name__ == '__main__':
    app.run(debug=True)
