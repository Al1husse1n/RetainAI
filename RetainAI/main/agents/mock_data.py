from faker import Faker
import random
import csv
import json

fake = Faker()

NUM_GUESTS = 48

events = ["anniversary", "birthday", None]
room_types = ["standard", "deluxe", "suite", "ocean view"]
services = ["spa", "dinner", "gym", "pool", None]
complaints = ["spa unavailable", "late check-in", "dirty room", None]
countries = ["USA", "UK", "Germany", "France", "Ethiopia", "UAE"]

def generate_guest():
    spend = random.randint(10, 5000)
    last_visit = random.randint(1, 200)

    had_complaint = random.choice([True, False])

    guest = {
        "id": fake.uuid4(),
        "name": fake.name(),
        "email": fake.email(),
        "total_spend": spend,
        "last_visit_days": last_visit,
        "visit_count": random.randint(1, 10),
        "event": random.choice(events),
        "room_preference": random.choice(room_types),
        "favorite_service": random.choice(services),
        "had_complaint": had_complaint,
        "complaint_type": random.choice(complaints) if had_complaint else None,
        "cancellation_count": random.randint(0, 3),
        "country": random.choice(countries)
    }

    return guest


# Generate random guests
guests = [generate_guest() for _ in range(NUM_GUESTS)]

# 🔥 Inject special demo guests (VERY IMPORTANT)
guests.append({
    "id": "demo-1",
    "name": "Mr. and Mrs. Wilson",
    "email": "wilsons@example.com",
    "total_spend": 3200,
    "last_visit_days": 73,
    "visit_count": 3,
    "event": "anniversary",
    "room_preference": "ocean view",
    "favorite_service": "dinner",
    "had_complaint": False,
    "complaint_type": None,
    "cancellation_count": 0,
    "country": "USA"
})

guests.append({
    "id": "demo-2",
    "name": "Jennifer Wu",
    "email": "jennifer@example.com",
    "total_spend": 800,
    "last_visit_days": 45,
    "visit_count": 2,
    "event": None,
    "room_preference": "deluxe",
    "favorite_service": "spa",
    "had_complaint": True,
    "complaint_type": "spa unavailable",
    "cancellation_count": 0,
    "country": "UK"
})

#Save to JSON
with open("guests.json", "w") as f:
    json.dump(guests, f, indent=2)

#Save to CSV
keys = guests[0].keys()

with open("guests.csv", "w", newline='') as f:
    writer = csv.DictWriter(f, fieldnames=keys)
    writer.writeheader()
    writer.writerows(guests)

print(f"Generated {len(guests)} guests")
print("Files saved: guests.json, guests.csv")