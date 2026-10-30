"""Create a demo user with two weeks of realistic activity. Usage: python -m scripts.seed_demo"""

from datetime import date, timedelta

from app.config import get_settings
from app.engine import Activity
from app.store import Store


def seed(store: Store, name: str = "Demo User") -> str:
    user = store.create_user(name)
    today = date.today()
    for n in range(14):
        day = today - timedelta(days=n)
        if day.weekday() < 5:
            store.add_activity(user.id, Activity(key="car_petrol", quantity=24, unit="km", occurred_on=day, description="commute"))
        if n % 2 == 0:
            store.add_activity(user.id, Activity(key="chicken", quantity=0.3, unit="kg", occurred_on=day))
        store.add_activity(user.id, Activity(key="rice", quantity=0.25, unit="kg", occurred_on=day))
        store.add_activity(user.id, Activity(key="electricity_grid", quantity=8, unit="kWh", occurred_on=day))
    store.add_activity(user.id, Activity(key="lpg", quantity=1, unit="cylinder", occurred_on=today - timedelta(days=9)))
    store.add_activity(user.id, Activity(key="flight_domestic", quantity=1150, unit="km",
                                         occurred_on=today - timedelta(days=5), description="Mumbai to Delhi"))
    store.add_activity(user.id, Activity(key="waste_landfill", quantity=12, unit="kg", occurred_on=today - timedelta(days=3)))
    store.add_activity(user.id, Activity(key="clothing_item", quantity=2, unit="item", occurred_on=today - timedelta(days=7)))
    return user.id


if __name__ == "__main__":
    user_id = seed(Store(get_settings().database_url))
    print(f"Demo user id: {user_id}")
    print("In the browser console on the app, run:")
    print(f"  localStorage.setItem('ecotrack.userId', JSON.stringify('{user_id}')); location.reload()")
