from app import app, db, Item

with app.app_context():
    Item.query.delete()
    db.session.commit()
    print("🗑️ All items deleted successfully.")
