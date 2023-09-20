from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait

if chrome:
    # If you want to open Chrome
    driver = webdriver.Chrome()
else:
    # If you want to open Firefox
    driver = webdriver.Firefox()

USERNAME_METHOD = "id"
PASSWORD_METHOD = "id"
SUBMIT_METHOD = "class"

USERNAME_FIELD = "input-1"
PASSWORD_FIELD = "input-2"
SUBMIT_FIELD = "loginButton"

username = driver.find_element_by_id(USERNAME_ID)
password = driver.find_element_by_id(PASSWORD_ID)
username.send_keys(USERNAME)
password.send_keys(PASSWORD)
driver.find_element_by_class(SUBMIT_ID).click()
