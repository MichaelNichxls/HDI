import argparse
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

LOGGER = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("sheet_imports", nargs="+", help="name of google sheets to import after scraping in order of precedence")
    parser.add_argument("-a", "--service_account_file", default="service_account.json", help="path of google service account json file")
    parser.add_argument("-i", "--spreadsheet_id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-s", "--sheet", default="Sheet1", help="name of google sheet to write the data to")

    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.service_account_file, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    values = {
        column[0].strip(): column[1:]
        for column in sheets.spreadsheets().values().get(
            spreadsheetId=args.spreadsheet_id,
            range=args.sheet,
            majorDimension="COLUMNS",
            valueRenderOption="FORMULA"
        ).execute()["values"]
    }
    values = {
        k: v + [""] * (len(values["Name"]) - len(v))
        for k, v in values.items()
    }
    name_to_index = {name: i for i, name in enumerate(values["Name"])}

    for sheet_import in reversed(args.sheet_imports):
        value_imports = {
            # NOTE: i really want this to be header, *v
            column[0].strip(): column[1:]
            for column in sheets.spreadsheets().values().get(
                spreadsheetId=args.spreadsheet_id,
                range=sheet_import,
                majorDimension="COLUMNS"
            ).execute()["values"]
            if column
        }
        value_imports["Name"] = (
            [
                f"{first.strip()} {last.strip()}"
                for first, last in zip(value_imports["First Name"], value_imports["Last Name"], strict=True)
            ]
            if {"First Name", "Last Name"} <= value_imports.keys()
            else value_imports["Name"]
        )
        value_imports = {
            k: v + [""] * (len(value_imports["Name"]) - len(v))
            for k, v in value_imports.items()
        }
        # TODO: handle "Name (Position)"
        # TODO: case-insensitive matching
        for i, name in enumerate(value_imports["Name"]):
            if (j := name_to_index.get(name)) is None:
                continue

            for header in ["Client", "Phone", "Email", "Twitter", "DM Status"]:
                if header not in value_imports:
                    continue

                values[header][j] = value_imports[header][i].strip() or values[header][j]
        else:
            LOGGER.info("imported %s to %s", sheet_import, args.sheet)
    
    values["Email"] = [
        f"""=HYPERLINK("mailto:{email}", "{email}")"""
            if email and "=HYPERLINK" not in email
            else email
        for email in values["Email"]
    ]
    values["Twitter"] = [
        f"""=HYPERLINK("https://twitter.com/{twitter.lstrip("@")}", "{twitter}")"""
            if twitter and "=HYPERLINK" not in twitter
            else twitter
        for twitter in values["Twitter"]
    ]
    response = sheets.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=f"{args.sheet}!A2",
        valueInputOption="USER_ENTERED",
        body={
            "majorDimension": "COLUMNS",
            "values": [*values.values()]
        }
    ).execute()
    LOGGER.info("updated %i rows in %s", response["updatedRows"], args.sheet)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()