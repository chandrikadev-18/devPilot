from .auth import login_user

def get_user_by_id(user_id):
    return {"id": user_id, "username": "test_user"}

def get_all_users():
    return [{"id": 1, "username": "test_user"}]
