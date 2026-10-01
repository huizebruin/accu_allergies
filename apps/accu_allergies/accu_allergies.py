############################################################
#
# This class aims to get the Allergies information from Accuweather
#
# written to be run from AppDaemon for a HASS or HASSIO install
#
# Written: 30/04/2020
# Updated: 26/06/2020
# added postcode in addition to ID for some locations
############################################################

############################################################
#
# In the apps.yaml file you will need the following
# updated for your database path, stop ids and name of your flag
#
# accu_allergies:
#   module: accu_allergies
#   class: Get_Accu_Allergies
#   ACC_FILE: "./allergies"
#   ACC_FLAG: "input_boolean.get_allergies_data"
#   DEB_FLAG: "input_boolean.reset_allergies_sensor"
#   URL_ID: "21921"
#   URL_CITY: "canberra"
#   URL_COUNTRY: "au"
#   URL_LANG: "en"
#   URL_POSTCODE: ""
#   WEB_VER: "APRIL22"
#
# PRE APRIL 2022
# https://www.accuweather.com/en/au/canberra/21921/allergies-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/cold-flu-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/asthma-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/arthritis-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/migraine-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/sinus-weather/21921
#
# APRIL 2022
# https://www.accuweather.com/en/au/canberra/21921/health-activities/21921
#
############################################################

# import the function libraries for beautiful soup
import datetime
import re
import shelve
import urllib.parse

from bs4 import BeautifulSoup

import appdaemon.plugins.hass.hassapi as hass
import requests


class Get_Accu_Allergies(hass.Hass):

    ACC_FLAG = ""
    DEB_FLAG = ""
    URL_LANG = ""
    URL_COUNTRY = ""
    URL_CITY = ""
    URL_ID = ""
    URL_POSTCODE = ""
    WEB_VER = ""

    payload = {}
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    # "https://www.accuweather.com/URL_LANG/URL_COUNTRY/URL_CITY/URL_POSTCODE/health-activities/URL_ID"
    # url building
    url_base = "https://www.accuweather.com"

    # simple - asthma, arthritis, migraine, sinus
    url_txt_setsA = [
        ["/asthma-weather/", "asthma"],
        ["/arthritis-weather/", "arthritis"],
        ["/migraine-weather/", "migraine"],
        ["/sinus-weather/", "sinus"],
        ["/air-quality-index/", "air"],
    ]
    url_txt_setsB = [
        ["/health-activities/", "health"],
        ["/air-quality-index/", "air"],
    ]

    # extended - cold, flu, ragweed pollen, grass pollen, tree pollen, mold, dust
    url_txt_xtdA = [
        ["/allergies-weather/", "?name=ragweed-pollen", "ragweed"],
        ["/allergies-weather/", "?name=grass-pollen", "grass"],
        ["/allergies-weather/", "?name=tree-pollen", "tree"],
        ["/allergies-weather/", "?name=mold", "mold"],
        ["/allergies-weather/", "?name=dust-and-dander", "dust"],
        ["/cold-flu-weather/", "?name=common-cold", "cold"],
        ["/cold-flu-weather/", "?name=flu", "flu"],
    ]
    url_txt_xtdB = []

    icon_txt_set = {
        'Air Quality': 'air-purifier', 'Dust & Dander': 'weather-dust', 'Sinus Pressure': 'head-sync',
        'Asthma': 'head-dots-horizontal', 'Migraine': 'head-alert', 'Arthritis': 'bone',
        'Common Cold': 'head-snowflake', 'Flu': 'head-flash', 'Indoor Pests': 'bug',
        'Outdoor Pests': 'spider', 'Mosquitos': 'bee', 'Outdoor Entertaining': 'party-popper',
        'Lawn Mowing': 'mower', 'Composting': 'compost', 'Air Travel': 'airplane', 'Driving': 'car',
        'Fishing': 'fish', 'Running': 'run', 'Golf': 'golf', 'Biking & Cycling': 'bike',
        'Beach & Pool': 'beach', 'Stargazing': 'weather-night', 'Hiking': 'hiking', 'Tree Pollen': 'tree'
    }

    def cleanString(self, s):
        if isinstance(s, (list, tuple)):
            s = ''.join(str(x) for x in s)
        if not isinstance(s, str):
            s = str(s)
        retstr = ""
        for chars in s:
            retstr += self.removeNonAscii(chars)
        return retstr

    def removeNonAscii(self, s):
        return ''.join(i for i in s if ord(i) < 126 and ord(i) > 31)

    def _safe_text(self, node):
        if node is None:
            return ""
        text = node.get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text)

    def _set_entity(self, entity_id, value, friendly_name, icon="mdi:air-purifier", extra=None):
        attrs = {"icon": icon, "friendly_name": friendly_name}
        if extra:
            attrs.update(extra)
        self.set_state(entity_id, state=str(value), replace=True, attributes=attrs)

    def _find_metric_values(self, soup, selectors):
        values = []
        seen = set()
        for selector in selectors:
            for node in soup.select(selector):
                text = self._safe_text(node)
                if not text:
                    continue
                text = re.sub(r"\s+", " ", text).strip()
                if text and text not in seen:
                    seen.add(text)
                    values.append(text)
        return values

    def _parse_value_pair(self, soup):
        gauges = []
        for node in soup.select("div.gauge, div.aq-number, div.index-status-text, div.index-name, span.value, div.value"):
            text = self._safe_text(node)
            if text:
                gauges.append(text)
        if len(gauges) >= 2:
            return gauges[0], gauges[1]
        values = self._find_metric_values(soup, [
            "div.gauge",
            "div.aq-number",
            "div.index-status-text",
            "span.value",
            "div.value",
            "p.statement",
        ])
        if len(values) >= 2:
            return values[0], values[1]
        return "Unknown", "Unknown"

    # run to setup the system
    def initialize(self):
        self.ACC_FILE = self.args["ACC_FILE"]
        self.ACC_FLAG = self.args["ACC_FLAG"]
        self.DEB_FLAG = self.args["DEB_FLAG"]
        self.URL_LANG = self.args["URL_LANG"]
        self.URL_COUNTRY = self.args["URL_COUNTRY"]
        self.URL_CITY = self.args["URL_CITY"]
        self.URL_ID = self.args["URL_ID"]

        try:
            self.WEB_VER = self.args["WEB_VER"]
        except Exception:
            self.WEB_VER = ""

        try:
            self.URL_POSTCODE = self.args["URL_POSTCODE"]
        except Exception:
            self.URL_POSTCODE = self.URL_ID
        if self.URL_POSTCODE == "":
            self.URL_POSTCODE = self.URL_ID

        # this supports the two website variations
        if self.WEB_VER == "APRIL22":
            self.url_txt_sets = self.url_txt_setsB
            self.url_txt_xtd = self.url_txt_xtdB
        else:
            self.url_txt_sets = self.url_txt_setsA
            self.url_txt_xtd = self.url_txt_xtdA

        self.load_sensors()
        self.listen_state(self.get_all_data, self.ACC_FLAG, new="on")
        self.listen_state(self.set_acc_sensors, self.DEB_FLAG, new="on")

        runtime = datetime.time(5, 7, 0)
        self.run_daily(self.daily_load_sensors, runtime)

    # get the information from each of the pages and write them into text files for reuse
    def get_all_data(self, entity, attribute, old, new, kwargs):
        self.get_html_data()
        self.turn_off(self.ACC_FLAG)

    # request the website information
    def get_html_data(self):
        start_url = self.url_base + "/" + self.URL_LANG + "/" + urllib.parse.quote(self.URL_COUNTRY) + "/" + urllib.parse.quote(self.URL_CITY) + "/" + self.URL_POSTCODE

        for sets in self.url_txt_sets:
            data_url = start_url + sets[0] + self.URL_ID
            self.get_data(data_url, sets[1])

        for sets in self.url_txt_xtd:
            data_url = start_url + sets[0] + self.URL_ID + sets[1]
            self.get_data(data_url, sets[2])

    # request the website information and write it to a file
    def get_data(self, url, txt):
        self.log("request " + url)
        try:
            data_from_website = self.get_html(url)
            if not data_from_website or len(data_from_website) < 200:
                self.log("No useful HTML returned for " + url)
                return False
            with shelve.open(self.ACC_FILE) as allergies_db:
                allergies_db[txt] = data_from_website
            self.set_get_sensor()
            self.create_get_sensor()
            return True
        except Exception as err:
            self.log(f"Error fetching {url}: {err}")
            return False

    def set_get_sensor(self):
        tim = datetime.datetime.now()
        date_time = tim.strftime("%d/%m/%Y, %H:%M:%S")
        with shelve.open(self.ACC_FILE) as allergies_db:
            allergies_db["updated"] = date_time

    def create_get_sensor(self):
        try:
            with shelve.open(self.ACC_FILE) as allergies_db:
                date_time = allergies_db["updated"]
        except Exception:
            date_time = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
        self.set_state("sensor.acc_data_last_sourced", state=date_time, replace=True, attributes={"icon": "mdi:timeline-clock-outline", "friendly_name": "ACC Allergy Data last sourced"})

    # get the html from the website
    def get_html(self, url):
        response = requests.get(url, headers=self.headers, timeout=25)
        response.raise_for_status()
        return response.text

    def set_acc_sensors(self, entity, attribute, old, new, kwargs):
        self.load_sensors()
        self.turn_off(self.DEB_FLAG)

    def load_sensors(self):
        collect_flag = 0
        try:
            with shelve.open(self.ACC_FILE) as allergies_db:
                if "updated" not in allergies_db:
                    collect_flag = 1
        except Exception:
            collect_flag = 1

        if collect_flag == 1:
            self.get_html_data()

        if self.WEB_VER == "APRIL22":
            self.get_vals(self.url_txt_sets[0][1])
            self.get_allergies_air_info(self.url_txt_sets[1][1])
        else:
            try:
                self.get_allergies_rag_info(self.url_txt_xtd[0][2])
                self.get_allergies_grass_info(self.url_txt_xtd[1][2])
                self.get_allergies_tree_info(self.url_txt_xtd[2][2])
                self.get_allergies_mold_info(self.url_txt_xtd[3][2])
                self.get_allergies_dust_info(self.url_txt_xtd[4][2])
                self.get_coldflu_cold_info(self.url_txt_xtd[5][2])
                self.get_coldflu_flu_info(self.url_txt_xtd[6][2])
            except Exception as err:
                self.log(f"Unable to parse extended data: {err}")

            try:
                self.get_allergies_air_info(self.url_txt_sets[4][1])
            except Exception as err:
                self.log(f"Unable to parse air data: {err}")

            try:
                self.get_asthma_info(self.url_txt_sets[0][1])
                self.get_arthritis_info(self.url_txt_sets[1][1])
                self.get_migraine_info(self.url_txt_sets[2][1])
                self.get_sinus_info(self.url_txt_sets[3][1])
            except Exception as err:
                self.log(f"Unable to parse named health data: {err}")

        self.create_get_sensor()

    def daily_load_sensors(self, kwargs):
        self.get_html_data()
        self.load_sensors()

    def get_vals(self, txt):
        try:
            with shelve.open(self.ACC_FILE) as allergies_db:
                html_info = allergies_db[txt]
        except Exception:
            self.log(f"No data available for {txt}")
            return

        soup = BeautifulSoup(html_info, "html.parser")
        myvals = soup.select("div.index-name")
        mytext = soup.select("div.index-status-text")

        if not myvals or not mytext:
            self.log(f"No valid index cards found for {txt}")
            return

        for val, text in zip(myvals, mytext):
            value = self._safe_text(text)
            name = self._safe_text(val)
            senid = "sensor.acc_" + name.lower().replace(" ", "_").replace("&", "and") + "_today"
            icon = self.icon_txt_set.get(name, 'mdi:air-purifier')
            self._set_entity(senid, value, name + " Today", "mdi:" + icon)

    def get_allergies_air_info(self, txt):
        try:
            with shelve.open(self.ACC_FILE) as allergies_db:
                html_info = allergies_db[txt]
        except Exception:
            self.log(f"No data available for {txt}")
            return

        soup = BeautifulSoup(html_info, "html.parser")
        values = self._find_metric_values(soup, [
            "div.aq-number",
            "div.gauge",
            "span.value",
            "div.value",
            "p.statement",
        ])

        today = values[0] if len(values) > 0 else "Unknown"
        tomorrow = values[1] if len(values) > 1 else "Unknown"
        self._set_entity("sensor.acc_air_today", today, "Air Quality Today", "mdi:air-purifier")
        self._set_entity("sensor.acc_air_tomorrow", tomorrow, "Air Quality Tomorrow", "mdi:air-purifier")

    def _set_metric_pair(self, sensor_name, friendly_name, icon, txt):
        try:
            with shelve.open(self.ACC_FILE) as allergies_db:
                html_info = allergies_db[txt]
        except Exception:
            self.log(f"No data available for {txt}")
            return

        soup = BeautifulSoup(html_info, "html.parser")
        value1, value2 = self._parse_value_pair(soup)
        self._set_entity(sensor_name + "_today", value1, friendly_name + " Today", icon, {"today_" + sensor_name + "_value": value1})
        self._set_entity(sensor_name + "_tomorrow", value2, friendly_name + " Tomorrow", icon, {"tomorrow_" + sensor_name + "_value": value2})

    def get_allergies_rag_info(self, txt):
        self._set_metric_pair("acc_ragweed_pollen", "Ragweed Pollen", "mdi:clover", txt)

    def get_allergies_grass_info(self, txt):
        self._set_metric_pair("acc_grass_pollen", "Grass Pollen", "mdi:barley", txt)

    def get_allergies_tree_info(self, txt):
        self._set_metric_pair("acc_tree_pollen", "Tree Pollen", "mdi:tree-outline", txt)

    def get_allergies_mold_info(self, txt):
        self._set_metric_pair("acc_mold", "Mold", "mdi:bacteria-outline", txt)

    def get_allergies_dust_info(self, txt):
        self._set_metric_pair("acc_dust", "Dust", "mdi:cloud-search-outline", txt)

    def get_coldflu_cold_info(self, txt):
        self._set_metric_pair("acc_common_cold", "Common Cold", "mdi:snowflake-alert", txt)

    def get_coldflu_flu_info(self, txt):
        self._set_metric_pair("acc_flu", "Flu", "mdi:bacteria", txt)

    def get_asthma_info(self, txt):
        self._set_metric_pair("acc_asthma", "Asthma", "mdi:lungs", txt)

    def get_arthritis_info(self, txt):
        self._set_metric_pair("acc_arthritis", "Arthritis", "mdi:bone", txt)

    def get_migraine_info(self, txt):
        self._set_metric_pair("acc_migraine", "Migraine", "mdi:head-flash", txt)

    def get_sinus_info(self, txt):
        self._set_metric_pair("acc_sinus", "Sinus", "mdi:head-remove-outline", txt)
