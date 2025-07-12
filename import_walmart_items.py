import json
from app import db, Item, app

# Load JSON file
with open('walmart_items.json', 'r') as f:
    items_data = json.load(f)

# Insert into database
with app.app_context():
    for data in items_data:
        # Check if item already exists to avoid duplicates
        existing = Item.query.filter_by(name=data['name'].lower()).first()
        if not existing:
            item = Item(
                name=data['name'].lower(),
                cost=data['cost'],
                image_url=data['image_url'],
                calories=data['calories'],
                protein=data['protein'],
                discount=data['discount']
            )
            db.session.add(item)
    db.session.commit()
    print("✅ Walmart items imported successfully.")
