import os
import streamlit as st
import streamlit_authenticator as stauth
from openai import OpenAI
from dotenv import load_dotenv
from agents import CalorieEstimator, ResponseEncoder
from azure.data.tables import TableClient, TableServiceClient
import time
import json
import pandas as pd
from datetime import datetime

load_dotenv()


def calc_costs(input,output):
    return input*0.03/1000 + output*0.06/1000

def insert_calorie_row(entity_dict):
    connection_string = os.environ["CONNECTION_STRING"]
    service = TableServiceClient.from_connection_string(conn_str=connection_string)
    table_client = service.get_table_client(table_name="macros")
    entity = table_client.create_entity(entity=entity_dict)

def get_user_food_diary(user_email):
    connection_string = os.environ["CONNECTION_STRING"]
    table_client  = TableClient.from_connection_string(conn_str=connection_string,table_name = "macros")
    filter_condition = f"RowKey eq '{user_email}'"
    user_entities = table_client.query_entities(filter_condition)
    entities_list = [entity for entity in user_entities]
    df = pd.DataFrame(entities_list)
    return df


if 'see_save_button' not in st.session_state:
    st.session_state['see_save_button'] = False

if 'disable_picture' not in st.session_state:
    st.session_state['disable_picture'] = True

if 'response' not in st.session_state:
    st.session_state['response'] = ""


def reset_app_state():
    st.session_state['see_save_button'] = False
    st.session_state['response'] = ""

# Load from the user database
connection_string = os.environ["CONNECTION_STRING"]
table_client  = TableClient.from_connection_string(conn_str=connection_string,table_name = "userdetails")
user_entities = table_client.list_entities()

def make_credentials(user_entities):
    credentials = {"usernames":{e['username']:{
        "email":e['email'],
        "name":e['PartitionKey'],
        "password":e['hashed_password']} for e in user_entities}}
    return credentials


#Configure the authenticator
authenticator = stauth.Authenticate(
    make_credentials(user_entities),
    os.environ["COOKIE_NAME"],
    os.environ["COOKIE_KEY"],
    int(os.environ["EXPIRY"]),
)

name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status:

    authenticator.logout('Logout', 'main')
    st.markdown(f"<h1 style='text-align: center; color: black;'>Welcome {name}</h1>", unsafe_allow_html=True)
    st.write('Welcome to calorie counter! Take a picture of your food to get an estimated caloric value and macro nutrient profile and save to your personal food diary! Or look at your food diary to track your dietary macros.')
    photo_tab, food_diary_tab = st.tabs(['Photo','My Diary'])

    with photo_tab:
        picture = st.camera_input("Take a picture",on_change=reset_app_state)
        if picture:
            st.image(picture)
        
            details = st.text_input("Any more details you'd like to add? E.g., dish type, serving size etc. Details improves the estimate, but aren't needed")
            if details == "":
                details = "None"
            calculate = st.button("Calculate!")
            if calculate:
                with st.spinner('Analysing your food...'):
                    CE = CalorieEstimator(key = os.environ['OPENAI_API_KEY_GPT'])
                    response = CE.run(picture,details)
                    st.session_state['response'] = response

                st.write(st.session_state['response'].choices[0].message.content)
                st.session_state['see_save_button'] = True

        if st.session_state['see_save_button']:
            if st.button("Save to diary"):
                RE = ResponseEncoder(key = os.environ['OPENAI_API_KEY_GPT'])
                response = RE.run(st.session_state['response'].choices[0].message.content)

                try:
                    json_output = json.loads(response.choices[0].message.content)
                    new_row = {
                        u'PartitionKey':  str(int(time.time())),
                        u'RowKey': authenticator.credentials['usernames'][username]['email'],
                        u'Calories': json_output['Calories'],
                        u'Carbs': json_output['Carbs'],
                        u'Fats': json_output['Fats'],
                        u'Protein':json_output['Protein'],
                        u'ImageID': "sdadasdas",
                        u'RawResponse': str(st.session_state['response']),  
                        u'MealDescription':json_output['MealDescription']
                        }
                    insert_calorie_row(new_row)
                    
                    st.write("This has been saved to your food diary!")
                except:
                    st.error('Oops - something went wrong!')

    
    with food_diary_tab:
        email = authenticator.credentials['usernames'][username]['email']
        df_food = get_user_food_diary(email)
        df_food['Date'] = pd.to_datetime(df_food['PartitionKey'], unit='s',utc = False).dt.date
        st.dataframe(df_food.loc[:,['Date','MealDescription','Calories','Protein','Fats','Carbs']])

    
elif authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')

st.divider()
signuplink = os.environ["SIGNUP_LINK"]
st.markdown(f"Not registered? Sign up [here]({signuplink})")