import argparse
import csv
import logging
import os

from google import genai
from google.genai import types
from google.genai.errors import APIError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

LOGGER = logging.getLogger(__name__)
# TODO: logging
API_RETRY = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=2, max=32),
    retry=retry_if_exception_type(APIError),
    reraise=True,
)
SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "sports_analytics": types.Schema(type=types.Type.BOOLEAN, description="If the institution contains a master's degree for Sports Analysis"),
        "data_analytics": types.Schema(type=types.Type.BOOLEAN, description="If the institution contains a master's degree for Data Analysis"),
        "data_science": types.Schema(type=types.Type.BOOLEAN, description="If the institution contains a master's degree for Data Science"),
        "business_analytics": types.Schema(type=types.Type.BOOLEAN, description="If the institution contains a master's degree for Business Analysis"),
    },
    required=["sports_analytics", "data_analytics", "data_science", "business_analytics"],
)
CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())],
    response_mime_type="application/json",
    response_schema=SCHEMA,
)


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # fmt: off
    # TODO: support for structured outputs with built-in tools is available only to Gemini 3 series models
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-r", "--range", default="Sheet1!A1", metavar="RANGE", help="range within google spreadsheet to write the data to")
    parser.add_argument("--clear", action="store_true", help="clears range within google spreadsheet before writing the data; ranges are specified via the '-r, --range' flag")
    # fmt: on
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    if args.clear:
        clear = sheets.spreadsheets().values().clear(spreadsheetId=args.id, range=args.range).execute()
        LOGGER.info("%s Cleared", clear["clearedRange"])

    with open("institutions.csv", encoding="utf-8-sig") as f:
        institutions = [*csv.DictReader(f)]

    client = genai.Client()
    for institution in institutions:
        # TODO: rename, optimize
        response = API_RETRY(client.models.generate_content)(
            model="gemini-3.1-flash-lite",
            contents=f"Which master's degree does `{institution['Institution']}` contain?",
            config=CONFIG,
        )
        append = (
            sheets.spreadsheets()
            .values()
            .append(
                spreadsheetId=args.id,
                range=args.range,
                valueInputOption="USER_ENTERED",
                insertDataOption="OVERWRITE",
                body={"values": [[institution["Institution"], *response.parsed.values()]]},
            )
            .execute()
        )
        LOGGER.info("%s Updated %i row(s): %s", append["updates"]["updatedRange"], append["updates"]["updatedRows"], institution["Institution"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()


# INFO:httpx:HTTP Request: POST ht 8i9otps://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 200 OK"
# INFO:__main__:'Graduate Program Lookup'!A1371:E1371 Updated 1 row(s): Oconee Fall Line Technical College
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 200 OK"
# INFO:__main__:'Graduate Program Lookup'!A1372:E1372 Updated 1 row(s): Ogeechee Technical College
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 200 OK"
# INFO:__main__:'Graduate Program Lookup'!A1373:E1373 Updated 1 row(s): Savannah Technical College
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
# INFO:google_genai.models:AFC is enabled with max remote calls: 10.
# INFO:httpx:HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent "HTTP/1.1 429 Too Many Requests"
