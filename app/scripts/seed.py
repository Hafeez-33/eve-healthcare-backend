from decimal import Decimal
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest

SEED_CENTRES = [
    {
        "name": "Eve Diagnostics Central",
        "location": "Indiranagar, Bangalore",
        "contact_number": "+919876543210",
        "tests": [
            {
                "name": "Complete Blood Count (CBC)",
                "description": "Measures red/white blood cells and platelets",
                "price": Decimal("450.00"),
            },
            {
                "name": "Lipid Profile",
                "description": "Measures cholesterol and triglycerides",
                "price": Decimal("850.00"),
            },
            {
                "name": "Thyroid Stimulating Hormone (TSH)",
                "description": "Assesses thyroid gland function",
                "price": Decimal("500.00"),
            },
        ],
    },
    {
        "name": "Eve Diagnostics West",
        "location": "Malleshwaram, Bangalore",
        "contact_number": "+919876543211",
        "tests": [
            {
                "name": "Complete Blood Count (CBC)",
                "description": "Comprehensive hematology blood screening",
                "price": Decimal("500.00"),
            },
            {
                "name": "Vitamin D (25-OH)",
                "description": "Assesses vitamin D sufficiency and bone health",
                "price": Decimal("1200.00"),
            },
            {
                "name": "HbA1c",
                "description": "Average blood sugar levels over the past 2-3 months",
                "price": Decimal("600.00"),
            },
        ],
    },
]


def seed_database() -> None:
    """Seed initial diagnostic centres and tests idempotently."""
    db = SessionLocal()
    try:
        for centre_data in SEED_CENTRES:
            # Check if centre exists
            existing_centre = db.scalar(
                select(DiagnosticCentre).where(DiagnosticCentre.name == centre_data["name"])
            )
            if not existing_centre:
                centre = DiagnosticCentre(
                    name=centre_data["name"],
                    location=centre_data["location"],
                    contact_number=centre_data["contact_number"],
                )
                db.add(centre)
                db.flush()
                print(f"Created centre: {centre.name}")
            else:
                centre = existing_centre
                print(f"Centre already exists: {centre.name}")

            # Seed tests for this centre
            for test_data in centre_data["tests"]:
                existing_test = db.scalar(
                    select(DiagnosticTest).where(
                        DiagnosticTest.centre_id == centre.id,
                        DiagnosticTest.name == test_data["name"],
                    )
                )
                if not existing_test:
                    test = DiagnosticTest(
                        centre_id=centre.id,
                        name=test_data["name"],
                        description=test_data["description"],
                        price=test_data["price"],
                        is_active=True,
                    )
                    db.add(test)
                    print(f"  - Added test: {test.name} (INR {test.price})")
                else:
                    print(f"  - Test already exists: {existing_test.name}")

        db.commit()
        print("Database seed completed successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
