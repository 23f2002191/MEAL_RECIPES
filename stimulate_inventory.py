import random
import time
from app import app, db, Item

def simulate_changes():
    with app.app_context():
        items = Item.query.all()
        for item in random.sample(items, k=min(5, len(items))):  # update 5 random items
            # Simulate price fluctuation between -10% to +10%
            fluctuation = random.uniform(-0.1, 0.1)
            item.cost = round(max(0.5, item.cost * (1 + fluctuation)), 2)

            # Simulate discount changes: 0%, 5%, 10%, 15%, or 20%
            item.discount = random.choice([0, 5, 10, 15, 20])

        db.session.commit()
        print("🔁 Inventory updated.")

if __name__ == '__main__':
    while True:
        simulate_changes()
        time.sleep(30)  # Every 30 seconds
