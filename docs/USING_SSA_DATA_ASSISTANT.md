# How to Use SSA Data Assistant

Welcome! This guide shows you how to ask questions, what each dataset represents, and the current guardrails when querying the SSA data warehouse.

## Table of Contents
- [Launch the App](#launch-the-app)
- [Pick a Dataset](#pick-a-dataset)
- [Ask a Question](#ask-a-question)
- [View SQL & Results](#view-sql--results)
- [Example Questions](#example-questions)
- [Limits & Tips](#limits--tips)

---

## Launch the App
Open the internal URL assigned to SSA Data Assistant—typically:

```
https://<your-app-host>   # ask Solutions CoE if unsure
```

You’ll see the familiar interface with:
- Dataset dropdown
- Question text area
- “Ask” button
- Optional “Show SQL” checkbox
- Download CSV button (enabled after results load)

---

## Pick a Dataset
Select the dataset you want to explore from the dropdown:

| Dataset       | Description                                                                 |
|---------------|-----------------------------------------------------------------------------|
| **Clients**       | Client firm profiles, industries, contacts, engagements linkage           |
| **Consultants**   | Internal + contractor roster, titles, capabilities, tool experience       |
| **Engagements**   | Project history, start/end dates, linked clients, team members            |
| **Training**      | Courses, capabilities taught, associated tools/resources                  |
| **Auto-detect**   | (If available) let the assistant infer the dataset from your question     |

*Tip:* Use the most relevant dataset to steer the assistant toward the correct tables.

---

## Ask a Question
Type a natural-language question, then click **Ask** (or press <kbd>Enter</kbd>).

Good questions:
- reference concrete entities (“clients in biotech”, “consultants who have control tower skills")
- mention metrics/columns you care about (“industries”, “start date”, “role rank”)
- specify ordering or filters if relevant (“latest 10”, “after 2023-01-01”)

Avoid:
- CREATE/UPDATE/DELETE requests (the assistant is read-only)
- Extremely broad questions with no context (“Tell me everything”)

---

## View SQL & Results
After a successful request, you’ll see:
1. **Status line** – e.g., “Done • 12 row(s)”
2. **Results table** – sortable by copy/paste
3. **Show SQL** (optional) – reveals the generated SQL
4. **Download CSV** – exports the current grid

Use “Show SQL” to review or reuse the query. All SQL is read-only and schema-qualified (e.g., `"Project_Master_Database"."ClientList"`).

---

## Example Questions

### Clients
```
List the top 10 clients by number of active engagements.
```
```
Show client firm name, primary contact name, and email for healthcare clients.
```

### Consultants
```
Which consultants have control tower experience and are Senior Manager level?
```
```
Show consultants, their titles, and the capabilities they cover.
```

### Engagements
```
List the five most recent engagements for AIG with start date and status.
```
```
Show engagement name, client firm, and team member names.
```

### Training
```
List training courses that teach “Data Visualization” capabilities.
```
```
Show training courses, associated tools, and links to the material.
```

Feel free to experiment—if the assistant misunderstands, rephrase with more context (“after 2022”, “Consultants dataset”).

---

## Limits & Tips
- **Read-only**: the assistant never modifies data. All queries are `SELECT`.
- **Schema awareness**: limited to what’s in the catalog (Project_Master_Database). New tables require a catalog refresh.
- **Timeouts**: queries have a short statement timeout (default 10s). Summaries on extremely large joins may truncate or timeout.
- **Ambiguity**: if results don’t look right, double-check the SQL (Show SQL) and clarify the question.
- **Security**: only authenticated internal users should access the app; credentials and API keys stay server-side.
