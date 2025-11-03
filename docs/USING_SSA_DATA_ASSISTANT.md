# How to Use SSA Data Assistant

Welcome! This guide shows you how to ask questions, what each dataset represents, and the guardrails in place when querying the SSA data warehouse.

## Table of Contents
- [Launch the App](#launch-the-app)
- [Pick a Dataset](#pick-a-dataset)
- [Ask a Question](#ask-a-question)
- [View SQL & Results](#view-sql--results)
- [Example Questions](#example-questions)
- [Limits & Tips](#limits--tips)

---

## Launch the App
Open the internal URL assigned to SSA Data Assistant (ask the Solutions CoE if unsure):

```
https://<your-app-host>
```

You will see the interface with:
- A sticky header containing the SSA logo, title, and the dark-mode toggle
- Dataset dropdown
- Question text box and **Submit** button
- **Common Queries** dropdown populated from recent usage

---

## Pick a Dataset
Select the dataset you want to explore from the dropdown:

| Dataset       | Description                                                                 |
|---------------|-----------------------------------------------------------------------------|
| **Clients**       | Client firm profiles, industries, contacts, engagement linkage             |
| **Consultants**   | Internal + contractor roster, titles, capabilities, tool experience        |
| **Engagements**   | Project history, start/end dates, linked clients, team members             |
| **Training**      | Courses, capabilities taught, associated tools/resources                   |
| **Auto (blank)**  | Leave empty to let the assistant infer the best fit                        |

*Tip:* Use the most relevant dataset to steer the assistant toward the correct tables.

---

## Ask a Question
Type a natural-language question, then click **Submit** (or press <kbd>Enter</kbd>).

Good questions:
- reference concrete entities ("clients in biotech", "consultants who have control tower skills")
- mention metrics/columns you care about ("industries", "start date", "role rank")
- specify ordering or filters if relevant ("latest 10", "after 2023-01-01")

Avoid:
- CREATE/UPDATE/DELETE requests (the assistant is read-only)
- Extremely broad questions with no context ("Tell me everything")

You can also pick a prompt from **Common Queries** to auto-fill the text box and adjust it before submitting.

---

## View SQL & Results
After a successful request, you will see:
1. **Row banner** – e.g., "12 rows returned" (or "No rows returned" if empty)
2. **Results table** – copy cells directly or use keyboard shortcuts
3. **View SQL Query** accordion – click to reveal the generated SQL
4. **Copy SQL** button – copies the SQL to the clipboard with a toast confirmation

All SQL is read-only and schema-qualified (for example `"Project_Master_Database"."ClientList"`).

---

## Example Questions

### Clients
```
List the top 10 clients by number of active engagements.
```
```
Show client firm name, contact name, email, and the resource who knows them for AIG.
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
List training courses that teach "Data Visualization" capabilities.
```
```
Show training courses, associated tools, and links to the material.
```

---

## Limits & Tips
- **Read-only**: the assistant never modifies data. All queries are `SELECT`.
- **Schema awareness**: limited to what is in the catalog (`Project_Master_Database`). New tables require a catalog refresh.
- **Timeouts**: queries have a short statement timeout (default 10s). Very large joins may truncate or timeout.
- **Ambiguity**: if results do not look right, review the SQL and clarify the question.
- **Security**: only authenticated internal users should access the app; credentials and API keys stay server-side.
- **Common queries**: the dropdown is powered by `/analytics/common-queries`. Selecting one auto-fills the prompt.
- **Problem queries**: empty or error responses are logged for tuning and can be reviewed at `/admin/problem-queries` (admin-only).
