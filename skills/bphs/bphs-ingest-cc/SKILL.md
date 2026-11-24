---
name: "bphs-ingest-cc"
description: "Turn a BPHS Chase credit-card workbook (Transactions + Accounts tabs) into a Chase Bank bill-import CSV (Bill Numbers CHS-#####), totals per short-code and program 600-611. Use on bphs-ingest-cc, Chase statement, credit card bill."
---

# BPHS Ingest CC (Chase)

Turn one or more monthly Chase card workbooks (`Chase-<Month>-<YYYY>.xlsx`) into one bill-import CSV for vendor **Chase Bank**. The user uploads that CSV to QuickBooks. Do not create bills through the QuickBooks API.

## Inputs

Each workbook has two tabs:

- `Transactions`: `Date, Description, Type, Prog, Amount`. `Type` is the short-code (the header can also be `Short-Code`). `Prog` is the 3-digit program.
- `Accounts`: `Short-Code, Account-Number-Base, Account-Text-Base` (example: `OS, 6032, OFFICE SUPPLIES EXPENSE`).

Uploaded files can carry a prefix (`93670f78-Chase-January-2026.xlsx`). Copy each file into a clean folder with its real name before you run the script.

## Rules

- One bill per workbook. One line per short-code + program with a non-zero total. Do not write zero lines.
- Account = `<base>-<prog> <Account-Text-Base>-<SITE>`. Example: OS on 600 → `6032-600 OFFICE SUPPLIES EXPENSE-ADMIN`.
- Short-codes ignore case and spaces (`FUEl` = `FUEL`).
- The bill date is the latest `Date` on the Transactions tab (the statement closing date). The user can override it with `--bill-date MM/DD/YYYY`.
- The sum of the lines must equal the sum of the Transactions `Amount` column.
- **Stop and ask** if a short-code is not on the Accounts tab, a program is outside 600–611, a row is missing a value, a line nets negative, or an account does not exist in QuickBooks. Do not guess an account.
- A short-code missing from the Accounts tab can be added for one run with `--extra-code CODE=BASE:TEXT`, only after the user approves. Tell the user to add it to the Accounts tab. Known case: `GAS=6070:UTILITIES-GAS/OIL` (approved for January 2026).
- Bill Numbers are `CHS-#####`, one per workbook, oldest bill date first. The skill folder cannot store the counter. Ask the user for the first number of this batch and suggest the one after the last batch. The first bill ever issued was `CHS-10001` (January 2026).

## Sites

| Program | Site | Program | Site |
| --- | --- | --- | --- |
| 600 | ADMIN | 606 | MARY-STREET |
| 601 | MARKET-STREET | 607 | COLLEGE-LANE |
| 602 | 19TH-STREET | 608 | TROLLEY-STREET |
| 603 | YOUGH-STREET | 609 | 10TH-STREET |
| 604 | AGNEW-ROAD | 610 | STATE-RTE-981 |
| 605 | VINE-STREET | 611 | WEST-2ND-AVE |

## Check names against QuickBooks

QuickBooks names drift (example: `6030-606 FOOD/GROCERY Expense-MARY-STREET` has a lowercase word), and some bases skip a site (6070 has no 608). If QuickBooks Labs is connected:

1. Run the script once without `--qbo-names` to see which account numbers the bill needs.
2. For each base number used, run `accounts_search` with `text: "<base>"` (read only).
3. Write `/tmp/cc-in/qbo_accounts.csv` with columns `Account Number,Name`, one row per number the bill needs, `Name` copied exactly from `name`.
4. Run again with `--qbo-names`. The script uses the exact QuickBooks name and stops if a number is missing.

If QuickBooks Labs is not connected, run without `--qbo-names` and tell the user the names were not checked.

## Workflow

1. Ask for the first Bill Number if the user has not given it.
2. Copy the workbooks into `/tmp/cc-in/` under their real names. Write the script below to `/tmp/cc_bill.py`.
3. Run it:

   ```bash
   python3 -I /tmp/cc_bill.py --start-bill CHS-10001 --output-dir <outputs-dir> \
     --qbo-names /tmp/cc-in/qbo_accounts.csv /tmp/cc-in/Chase-*.xlsx
   ```

4. If it prints `STOP`, show the user each problem and wait.
5. On success it writes `Chase-<MMDDYYYY>-....csv` (bill dates, oldest first). Send that file. Report each bill's number, date, total and line count, and the next Bill Number.

Output columns: `Bill Number, Vendor, *Bill Date, *Type, Category/Account, Description, Amount`. `Vendor` is on the first row of each bill only. `*Type` is `Category Details`. Description is `Chase MM/DD/YYYY <CODE> (<n> charges)`. Amounts are `1234.56` with no `$` and no commas.

Do not put the script or `qbo_accounts.csv` in the outputs folder.

## Script

```python
#!/usr/bin/env python3
"""Build a Chase Bank bill-import CSV from BPHS Chase card workbooks.

One bill per workbook. Each workbook has a Transactions tab
(Date, Description, Type/Short-Code, Prog, Amount) and an Accounts tab
(Short-Code, Account-Number-Base, Account-Text-Base). Amounts are totaled per
short-code and program; each total is one bill line on
<base>-<prog> <TEXT>-<SITE>. Stops on any unknown short-code, bad program,
missing value, negative line, or total mismatch.
"""
import argparse, csv, sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import openpyxl

VENDOR = "Chase Bank"
PREFIX = "CHS-"
SITES = {
    "600": "ADMIN", "601": "MARKET-STREET", "602": "19TH-STREET",
    "603": "YOUGH-STREET", "604": "AGNEW-ROAD", "605": "VINE-STREET",
    "606": "MARY-STREET", "607": "COLLEGE-LANE", "608": "TROLLEY-STREET",
    "609": "10TH-STREET", "610": "STATE-RTE-981", "611": "WEST-2ND-AVE",
}
HEADER = ["Bill Number", "Vendor", "*Bill Date", "*Type", "Category/Account", "Description", "Amount"]
CENT = Decimal("0.01")


def money(v):
    if v is None or str(v).strip() == "":
        return None
    return Decimal(str(v).replace("$", "").replace(",", "").strip()).quantize(CENT, ROUND_HALF_UP)


def norm(s):
    return " ".join(str(s or "").split()).upper()


def prog_code(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def sheet(wb, name):
    for ws in wb.worksheets:
        if ws.title.strip().lower() == name.lower():
            return ws
    sys.exit(f"STOP: no '{name}' tab in workbook")


def rows_by_header(ws, wanted):
    """Yield (row_number, dict) using header names; wanted maps key -> accepted header names."""
    it = ws.iter_rows(values_only=True)
    head = [norm(h) for h in next(it)]
    col = {}
    for k, names in wanted.items():
        for n in names:
            if norm(n) in head:
                col[k] = head.index(norm(n))
                break
        else:
            sys.exit(f"STOP: '{ws.title}' tab has no {names[0]} column (found {head})")
    for i, r in enumerate(it, start=2):
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        yield i, {k: (r[c] if c < len(r) else None) for k, c in col.items()}


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v).strip(), "%m/%d/%Y").date()


def load_accounts(ws, extra, problems):
    acc = {}
    for i, r in rows_by_header(ws, {"code": ["Short-Code"], "num": ["Account-Number-Base"],
                                     "text": ["Account-Text-Base"]}):
        code, num, text = norm(r["code"]), prog_code(r["num"]), norm(r["text"])
        if not (code and num and text):
            problems.append(f"Accounts row {i}: missing Short-Code, number or text")
        elif code in acc:
            problems.append(f"Accounts row {i}: short-code {code} listed twice")
        else:
            acc[code] = (num, text)
    for e in extra:  # CODE=BASE:TEXT, one-off additions the user approved
        code, rest = e.split("=", 1)
        num, text = rest.split(":", 1)
        acc[norm(code)] = (num.strip(), norm(text))
    return acc


def load_qbo_names(path):
    """Optional CSV 'Account Number,Name' from QuickBooks; exact names win over generated ones."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["Account Number"].strip(): r["Name"].strip() for r in csv.DictReader(f)}


def build(path, accounts, qbo, bill_date_override, problems):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    tag = Path(path).name
    totals, counts, grand, dates = {}, {}, Decimal("0"), []
    for i, r in rows_by_header(sheet(wb, "Transactions"), {
            "date": ["Date"], "code": ["Short-Code", "Type"], "prog": ["Prog", "Program"],
            "amt": ["Amount"]}):
        code, prog, amt = norm(r["code"]), prog_code(r["prog"]), money(r["amt"])
        if amt is None or not code or not prog:
            problems.append(f"{tag} row {i}: missing short-code, program or amount")
            continue
        if code not in accounts:
            problems.append(f"{tag} row {i}: short-code '{code}' not on Accounts tab ({amt})")
        if prog not in SITES:
            problems.append(f"{tag} row {i}: program '{prog}' not in 600-611 ({amt})")
        if r["date"] is not None:
            dates.append(as_date(r["date"]))
        grand += amt
        totals[(code, prog)] = totals.get((code, prog), Decimal("0")) + amt
        counts[(code, prog)] = counts.get((code, prog), 0) + 1

    bill_date = bill_date_override or (max(dates) if dates else None)
    if bill_date is None:
        problems.append(f"{tag}: no dates found; pass --bill-date")
        return None
    lines = []
    for (code, prog), amt in totals.items():
        if code not in accounts or prog not in SITES or amt == 0:
            continue
        base, text = accounts[code]
        number = f"{base}-{prog}"
        if qbo is not None and number not in qbo:
            problems.append(f"{tag}: account {number} ({code}, program {prog}, {amt}) "
                            "does not exist in QuickBooks")
            continue
        name = qbo[number] if qbo else f"{text}-{SITES[prog]}"
        if amt < 0:
            problems.append(f"{tag}: {number} {code} nets negative ({amt}); ask how to post the credit")
        lines.append((number, f"{number} {name}", code, amt, counts[(code, prog)]))
    lines.sort()
    if sum(l[3] for l in lines) != grand and not problems:
        problems.append(f"{tag}: line sum {sum(l[3] for l in lines)} != transactions total {grand}")
    return {"tag": tag, "date": bill_date, "lines": lines, "total": grand}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-bill", required=True, help="first Bill Number, e.g. CHS-10001")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--bill-date", help="MM/DD/YYYY; only with one workbook. Default: latest Transactions date")
    ap.add_argument("--qbo-names", help="CSV 'Account Number,Name' read from QuickBooks")
    ap.add_argument("--extra-code", action="append", default=[],
                    help="CODE=BASE:TEXT for a short-code missing from the Accounts tab (user-approved)")
    ap.add_argument("files", nargs="+", help="Chase workbooks (.xlsx)")
    a = ap.parse_args()
    if a.bill_date and len(a.files) > 1:
        sys.exit("STOP: --bill-date works with one workbook only")

    problems, bills = [], []
    qbo = load_qbo_names(a.qbo_names) if a.qbo_names else None
    override = datetime.strptime(a.bill_date, "%m/%d/%Y").date() if a.bill_date else None
    for path in a.files:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        accounts = load_accounts(sheet(wb, "Accounts"), a.extra_code, problems)
        b = build(path, accounts, qbo, override, problems)
        if b:
            bills.append(b)

    if problems:
        print("STOP — fix these before writing a bill:", *problems, sep="\n  ")
        sys.exit(1)

    start = int(a.start_bill.upper().removeprefix(PREFIX))
    bills.sort(key=lambda b: b["date"])
    rows = []
    for n, b in enumerate(bills):
        b["no"] = f"{PREFIX}{start + n}"
        d = b["date"].strftime("%m/%d/%Y")
        for j, (_, account, code, amt, cnt) in enumerate(b["lines"]):
            rows.append([b["no"], VENDOR if j == 0 else "", d, "Category Details", account,
                         f"Chase {d} {code} ({cnt} charge{'s' if cnt != 1 else ''})", f"{amt:.2f}"])

    out = Path(a.output_dir) / ("Chase-" + "-".join(b["date"].strftime("%m%d%Y") for b in bills) + ".csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)

    for b in bills:
        print(f"{b['no']}  {b['date']:%m/%d/%Y}  {b['tag']}  total {b['total']:.2f}  ({len(b['lines'])} lines)")
        for _, account, code, amt, cnt in b["lines"]:
            print(f"  {code:<6} {account:<52} {amt:>10.2f}  [{cnt}]")
    print(f"Wrote {out}")
    print(f"Next Bill Number: {PREFIX}{start + len(bills)}")


if __name__ == "__main__":
    main()
```
