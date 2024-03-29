import pickle
import time
from datetime import date, timedelta
from io import StringIO

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd
import requests
from bs4 import BeautifulSoup

from scripts.librus.urls import HEADERS, API_URL, LESSONS_DONE_URL, LESSON_PLAN_URL

classes = {
    "2a": "81845",
    "3e": "78526",
    "4e": "76123",
}
subjects = {
    "informatyka": "20450",
    "COMP HL/SL": "71370",
    "COMP HL": "81858",
    "Mathematics applications and interpretation": "88275",
}
teachers = {
    "Adam Kucz": "1951391",
}

LOGIN_PAYLOAD = {
    "login": "adamkucz2lopoznan",
    "pass": ":L^}<w.H5Ui;[yg=Q\\&KXF!6rJsx)Ah\"f>P,}.zs4%\\+h?U^0",
    "action": "login"
}
LESSON_SUMMARY_PAYLOAD = {
    "requestkey": "", # from "value" parameter of input with name "requestkey"
    "tryb_pelnoekranowy": "0",
    "data_od": "", # format: "{year:4}-{month:2}-{day:2}",
    "data_do": "", # format: "{year:4}-{month:2}-{day:2}"
    "grupowanieWirtualnych": "on",
    "liczone_w_rpn": "-1",
    "id_dodającego": "-1",
    "id_zastępującego": "0",
    "filtruj_id_klasy": "-1",
    "filtruj_id_nauczyciela": "-1",
    "filtruj_id_przedmiotu": "-1",
    "filtrowanie_pojemnik": "1001",
    "filtruj": "Filtruj",
    "reczny_submit": "1"
}
LESSON_PLAN_PAYLOAD = {
    "requestkey": "", # from "value" parameter of input with name "requestkey"
    "rodzajPlanu": "1",
    "nauczyciel": "",
    "typWyswietlaniaPlanu": "1",
    "tydzien": "",  # format: "{year:4}-{month:2}-{day:2}_{year:4}-{month:2}-{day:2}", start_end, Mon_Sun
    "pokaz_zajecia_op": "on",
    "pokaz_zajecia_dzd": "on",
    "pokaz_zajecia_zsk": "on",
    #    "pokaz_zajecia_ni": "on",
}

headers = {
    "Authorization": "Basic Mjg6ODRmZGQzYTg3YjAzZDNlYTZmZmU3NzdiNThiMzMyYjE="
}


def login(session): # TODO: (possibly) debug
    session.get(API_URL + "/OAuth/Authorization?client_id=47&response_type=code&scope=mydata")
    login_response = session.post(API_URL + "/OAuth/Authorization?client_id=47", data=LOGIN_PAYLOAD)
    redirect_response = session.get(API_URL + login_response.json().get("goTo"))


def authenticate_browser(session):
    session.get(API_URL + "/OAuth/Authorization?client_id=47&response_type=code&scope=mydata")
    login_response = session.post(API_URL + "/OAuth/Authorization?client_id=47", data=LOGIN_PAYLOAD)
    redirect_response = session.get(API_URL + login_response.json().get("goTo"))
    soup = BeautifulSoup(redirect_response.text, "xml")
    code = soup.find("span", class_="twofa-code").text
    name = input(f"2FA, click the text '{code}' and then put in a memorable name for this session and press Enter: ")
    session.post(API_URL + "/OAuth/TwoFA/KLN?client_id=47",
                 files={'action': (None, 'performLogin'), 'trustedBrowser': (None, name)})
    session.get(f"{API_URL}/OAuth/Authorization/PerformLogin?client_id=47")


def get_summary_dataframe(html):
    html_tables = pd.read_html(StringIO(html))
    df = html_tables[1]
    df = df.drop(columns=["Klasa", "Data.1", "Nr lekcji", "Zajęcie Edukacyjne", "Podstawa programowa", "licz...", "RPN", "Operacje"])
    df = df[["Data", "ob", "nb", "Temat zajęć edukacyjnych"]]
    return df.dropna(axis=0, how="all").sort_values("Data")


def get_week_plan_dataframe(html):
    html_tables = pd.read_html(StringIO(html))
    df = html_tables[1]
    df = df.drop(columns=["Godziny"])
    df = df[["Data", "ob", "nb", "Temat zajęć edukacyjnych"]]
    return df.dropna(axis=0, how="all").sort_values("Data")


def save_summary_as_pdf(dataframe, filename, figsize=(21 / 2.54, 29.7 / 2.54)): # TODO: fix figure and font sizing
    dataframe = dataframe.astype({"ob": np.int8, "nb": np.int8})
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis('tight')
    ax.axis('off')
    the_table = ax.table(cellText=dataframe.values, colLabels=dataframe.columns, loc='top')
    for cell in the_table.get_celld().values():
        cell.set_text_props(ha="left")
    the_table.auto_set_font_size(False)
    the_table.set_fontsize(11)
    the_table.auto_set_column_width(col=list(range(len(dataframe.columns))))
    the_table.scale(2, 2)
    with PdfPages(f"{filename}.pdf") as pp:
        pp.savefig(fig, bbox_inches='tight', orientation="portrait")


def save_full_as_pdf(dataframes, filename, figsize=(21 / 2.54, 29.7 / 2.54)):
    pass


def get_one_from(name, mapping):
    keys = list(mapping)
    print(f"Choose {name}, known are:")
    for i, elem in enumerate(keys):
        print(f"{i}: {elem}")
    return mapping[keys[int(input("Choice: "))]]


def interactive(session):
    filters = LESSON_SUMMARY_PAYLOAD.copy()
    lessons_done_response = session.get(LESSONS_DONE_URL)
    soup = BeautifulSoup(lessons_done_response.text, "lxml")
    filters['request_key'] = soup.find("input", {'name': 'requestkey'}).get('value')
    filters['data_od'] = "20" + input("Give date to start at, in the YY-MM-DD format: ")
    filters['data_do'] = "20" + input("Give date to end at, in the YY-MM-DD format: ")
    filters['filtruj_id_nauczyciela'] = get_one_from("teacher", teachers)
    next_filter = "yes"
    while next_filter:
        class_ = input("Specify class as '\d[a-g]': ")
        filters["filtruj_id_klasy"] = classes[class_]
        filters['filtruj_id_przedmiotu'] = get_one_from("subject", subjects)
        filter_response = session.post(LESSONS_DONE_URL, data=filters)
        dataframe = get_summary_dataframe(filter_response.text)
        filename = input("Filename to save data as: ")
        save_summary_as_pdf(dataframe, filename)
        next_filter = input("Continue? Leave blank to finish.")


def from_data(session, filename):
    with open(filename, "r", encoding="utf-8") as datafile:
        lines = datafile.readlines()
    filetype = lines[0][:-1]
    if filetype == "lesson summary":
        lesson_summary_from_data(session, lines[1:])
    elif filetype == "full plan":
        full_plan_from_data(session, lines)


def full_plan_from_data(session, lines):
    dataframes = []

    filters = LESSON_PLAN_PAYLOAD.copy()
    lessons_done_response = session.get(LESSON_PLAN_URL)
    soup = BeautifulSoup(lessons_done_response.text, "lxml")
    filters['request_key'] = soup.find("input", {'name': 'requestkey'}).get('value')
    teacher = lines[0][:-1]
    date_from = date.fromisoformat(lines[1][:-1])
    original_date_from = date_from
    date_to = date.fromisoformat(lines[2][:-1])
    filters['nauczyciel'] = teachers[teacher]
    while date_from < date_to:
        filters['tydzien'] = f"{date_from}_{date_from + timedelta(days=6)}"
        response = session.post(LESSONS_DONE_URL, data=filters)
        dataframes.append(get_week_plan_dataframe(response.text))
        date_from += timedelta(days=6)
    filename = " ".join((original_date_from, "to", date_to, teacher))
    save_full_as_pdf(dataframes, filename)


def lesson_summary_from_data(session, lines):
    filters = LESSON_SUMMARY_PAYLOAD.copy()
    lessons_done_response = session.get(LESSONS_DONE_URL)
    soup = BeautifulSoup(lessons_done_response.text, "lxml")
    filters['request_key'] = soup.find("input", {'name': 'requestkey'}).get('value')
    teacher = lines[0][:-1]
    date_from = lines[1][:-1]
    date_to = lines[2][:-1]
    filters['filtruj_id_nauczyciela'] = teachers[teacher]
    filters['data_od'] = date_from
    filters['data_do'] = date_to
    for line in lines[3:]:
        class_, subject = line[:-1].split(",")
        filters["filtruj_id_klasy"] = classes[class_]
        filters['filtruj_id_przedmiotu'] = subjects[subject]
        filter_response = session.post(LESSONS_DONE_URL, data=filters)
        dataframe = get_summary_dataframe(filter_response.text)
        filename = " ".join((date_from, "to", date_to, teacher, class_, subject)).replace("/", " and ")
        save_summary_as_pdf(dataframe, filename)
    print("Remember to add lessons that were skipped and are not in Librus!")


def main():
    with requests.Session() as s:
        s.headers = HEADERS
        choice = input("File to load cookies from, will proceed to 2FA if empty: ")
        if not choice:
            authenticate_browser(s)
        else:
            with open(choice, "rb") as cookie_file:
                s.cookies.update(pickle.load(cookie_file))
            login(s)

        time.sleep(2)
        data = input("Give filename of file with data to download (empty for interactive): ")
        if not data:
            interactive(s)
        else:
            from_data(s, data)

        fileout = input("Save cookies in file (empty to not save): ")
        if fileout:
            with open(fileout, "wb") as cookie_file:
                pickle.dump(s.cookies, cookie_file)


main()
