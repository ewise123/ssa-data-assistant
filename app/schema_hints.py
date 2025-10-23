# app/schema_hints.py
# Short, human-readable descriptions of your DB schema.
# The model will get only one dataset's hint per request.

SCHEMA_HINTS = {
    "clients": """
    Table: clients
      - client_id (UUID, PK)
      - name (TEXT)
      - industry (TEXT)
      - created_at (TIMESTAMPTZ)
    Relationships:
      - One client has many client_contacts (client_contacts.client_id)
    """,

    "consultants": """
    Table: consultant_roster
      - consultant_id (UUID, PK)
      - name (TEXT)
      - email (TEXT)
      - phone_number (TEXT)
      - role (TEXT)
      - created_at (TIMESTAMPTZ)
    """,

    "engagements": """
    Table: engagements
      - engagement_id (UUID, PK)
      - client_id (UUID, FK→clients)
      - consultant_id (UUID, FK→consultant_roster)
      - start_date (DATE)
      - end_date (DATE)
      - status (TEXT)
    """
}
