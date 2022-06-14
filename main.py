import datetime
from typing import ClassVar
import pandas as pd
import plotly.io as pio
import psycopg2
import schedule as schedule
import sqlalchemy
import plotly
import plotly.graph_objs as go
from plotly.offline import iplot
import sqlite3
import numpy as np
import datetime as dt
from datetime import datetime, date, time, timedelta
import math
import warnings
import random as rnd
import kaleido
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, JobQueue
from sqlalchemy import Float
from sqlalchemy import Column, Integer, String, create_engine, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.session import sessionmaker, Session
from sqlalchemy.orm import relationship
from pytz import timezone
import datetime

print("Бот запущен.")


def morning(context: CallbackContext):
    message = "Доброе утро всем! Хорошего всем дня, не забывайте писать отчеты!"
    context.bot.send_message(chat_id=-1001636279290, text=message)


def evening(context: CallbackContext):
    message = "Спокойной ночи!😴 Ложитесь вовремя!"
    context.bot.send_message(chat_id=-1001636279290, text=message)


Base = declarative_base()
engine = create_engine('sqlite:///sz.db', echo=True)
Base.metadata.create_all(engine)
token = "5003896889:AAFlIPPPr7_-YFsN9_QO9nnO8W2e_L4ZSew"
updater = Updater(token, use_context=True)
Base = declarative_base()
j = updater.job_queue

job_daily = j.run_daily(morning, days=(0, 1, 2, 3, 4, 5, 6), time=datetime.time(9, 0, tzinfo=timezone('Europe/Moscow')))
j_daily = j.run_daily(evening, days=(0, 1, 2, 3, 4, 5, 6),
                      time=datetime.time(21, 30, tzinfo=timezone('Europe/Moscow')))


def check(a):
    if len(a) == 5:
        if int(a[0] + a[1]) < 24 and int(a[3]) < 6:
            return a + ":00"
    elif len(a) == 4:
        if int(a[2]) < 6:
            b = '0' + a + ":00"
            return b
    return ''


class Users(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    name_id = Column(String)
    idt = Column(Integer)
    time_g_start = Column(String)
    time_g_end = Column(String)
    users_shares = relationship("Sleep")


class Admin(Base):
    __tablename__ = 'admin'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    name_id = Column(String)
    idt = Column(Integer)


class Sleep(Base):
    __tablename__ = "sleep"
    id = Column(Integer, primary_key=True)
    time_start = Column(String)
    time_end = Column(String)
    date = Column(String)
    rate = Column(Integer)
    k = Column(Integer)
    points = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"))


class Tips(Base):
    __tablename__ = 'tips'
    id = Column(Integer, primary_key=True)
    text = Column(String)


def SendTip(count):
    with sessionmaker(bind=engine).begin() as session:
        s = session.query(Users).get(count)
        return s.text


def on_start(update, context):
    chat = update.effective_chat
    context.bot.send_message(chat_id=chat.id,
                             text="Привет, я твой помощник для сна. \nДля начала напиши во сколько ты хочешь ложиться и вставать под #цель\nЧтобы я смогу помочь тебе со сном утром под #утро пиши когда ты проснулся, во сколько лёг, ну и опиши свое состояние по шкале от 1 до 10")


def add(s, newansw):
    answ = s.split('\n')
    for i in range(int(len(answ))):
        answ[i] = answ[i].strip()
        for j in range(int(len(answ[i]))):
            if answ[i][j].isdigit() or answ[i][j] == ':' or answ[i][j] == '.':
                newansw[i - 1] += answ[i][j]
            # print(answ[i][j])
    newansw[0] = check(newansw[0])
    newansw[1] = check(newansw[1])
    return newansw


def prepare():
    conn = sqlite3.connect('sz.db')
    users = pd.read_sql("select * from users", conn)
    sleep = pd.read_sql("select * from sleep", conn)
    start_time = pd.to_datetime(sleep['time_start'])
    sleep['rate'] = sleep['rate'].astype(int)
    sleep['date'] = pd.to_datetime(sleep['date'], format='%Y-%m-%d')
    sleep['time_start'] = pd.to_timedelta(sleep['time_start'])
    sleep['time_end'] = pd.to_timedelta(sleep['time_end'])
    sleep['k'] = sleep['k'].fillna(0)
    sleep['k'] = sleep['k'].astype('float')
    sleep['points'] = sleep['points'].fillna(0)
    pd.options.mode.chained_assignment = None
    ref_time = time.fromisoformat('17:30:00')
    for i in range(sleep.shape[0]):
        real_time = start_time[i].time()
        if real_time > ref_time:
            sleep['time_start'][i] -= pd.Timedelta(days=1)
    return sleep, users


def prepare2(person_data):
    person_data['target_time_start'] = person_data['date'] + person_data['target_time_start']
    person_data['target_time_end'] = person_data['date'] + person_data['target_time_end']
    start = person_data['time_start'] + person_data['date']
    end = person_data['time_end'] + person_data['date']
    person_data['ttdiff_start'] = abs(person_data['target_time_start'] - start).astype('timedelta64[m]')
    person_data['ttdiff_end'] = abs(pd.Timedelta(days=0) - (person_data['target_time_end'] - end)).astype(
        'timedelta64[m]')
    return person_data


def sleep_k(diff_series, ind):
    groups = pd.qcut(range(15), 181, labels=False)
    if diff_series[ind] <= 180:
        for i in range(len(groups)):
            if diff_series[ind] < groups[i]:
                sleep_k = ((
                                       16 - i) * 0.02333)  # 0.04666 (*15 = 0.7) бонус поделили на 2, тк общий бонус состоит из 2 частей (подъем и отход ко сну)
                break
    return sleep_k


def strike_beginning(date_ser):
    beg_day = date_ser[date_ser.shape[0] - 1]
    for i in range(date_ser.shape[0] - 2, -1, -1):
        prev_day = date_ser[i]
        if (beg_day - prev_day) > pd.Timedelta(days=1):
            return i + 1
        else:
            beg_day = prev_day
    return 0


def check_k(person_data):
    for i in range(len(person_data['date'])):
        strike_days = 1
        if i >= 1:  # если до этого уже были дни с записями о прочтении отчетов, нужно учесть страйк
            last_strike_beg = strike_beginning(
                person_data['date'])  # последний день, когда отчета не было: со следующего считаем страйк дней
            strike_days = 1 * len(person_data['date'][last_strike_beg:i + 1])
            if (strike_days > 10): strike_days = 10  # максимальный страйк -- 10 дней
    return strike_days * 0.03


def smth(users, person_data, x):
    ind = users[users['id'] == x].index[0]
    tts = pd.to_timedelta(users[users['id'] == x]['time_g_start'][ind])
    ref_time = pd.Timedelta('17:30:00')
    if tts > ref_time:
        person_data['target_time_start'] = tts - pd.Timedelta(days=1)
    else:
        person_data['target_time_start'] = tts
    person_data['target_time_end'] = pd.to_timedelta(users[users['id'] == x]['time_g_end'][ind])
    return person_data


def onesleep(x):
    sleep, users = prepare()
    fig_sleep = go.Figure()
    person_data = sleep[sleep['user_id'] == x]
    person_data = person_data.drop_duplicates(subset=['date'])
    person_data = smth(users, person_data, x)
    fall_asleep_time_scale = (pd.Timestamp('now').normalize() + person_data['time_start']).reset_index(drop=True)
    wake_up_time_scale = (pd.Timestamp('now').normalize() + person_data['time_end']).reset_index(drop=True)
    wake_up_goal = (pd.Timestamp('now').normalize() + person_data['target_time_end']).reset_index(drop=True)
    fall_asleep_goal = (pd.Timestamp('now').normalize() + person_data['target_time_start']).reset_index(drop=True)

    wake_up_trace = go.Scatter(
        x=person_data['date'],
        y=wake_up_time_scale,
        name="Время подъема",
        marker_color='#21cfbd'
    )
    fall_asleep_trace = go.Scatter(
        x=person_data['date'],
        y=fall_asleep_time_scale,
        name="Время отхода ко сну",
        marker_color='#21cfbd',
        fill='tonexty'
    )
    fall_asleep_goal_trace = go.Scatter(
        x=person_data['date'],
        y=fall_asleep_goal,
        name='Целевое время подъема',
        marker_color='#000099',
        mode='lines',
        line=dict(dash='dash')
    )
    wake_up_goal_trace = go.Scatter(
        x=person_data['date'],
        y=wake_up_goal,
        name='Целевое время отхода ко сну',
        marker_color='#000099',
        mode='lines',
        line=dict(dash='dash')
    )
    fig_sleep.add_trace(wake_up_trace)
    fig_sleep.add_trace(fall_asleep_trace)
    fig_sleep.add_trace(fall_asleep_goal_trace)
    fig_sleep.add_trace(wake_up_goal_trace)
    fig_sleep.update_layout(
        title='График отхода ко сну и подъема',
        xaxis_tickformat='%d %B%Y',
        yaxis_tickformat='%H:%M',
        font_size=12
    )
    fig_sleep.update_yaxes(
        autorange='reversed'
    )
    pio.write_image(fig_sleep, r"fig.jpeg")


def ratesleep(x):
    sleep, users = prepare()
    fig_rates = go.Figure()
    person_data = sleep[sleep['user_id'] == x]
    person_data = person_data.drop_duplicates(subset=['date'])
    person_data = person_data.reset_index(drop=True)
    clrs = []
    for i in range(person_data.shape[0]):
        if person_data['rate'][i] < 5:
            clrs.append('#2FB0A4')
        elif person_data['rate'][i] <= 7:
            clrs.append('#34C1B4')
        else:
            clrs.append('#6DD8CE')

    trace = go.Bar(x=person_data['date'],
                   y=person_data['rate'],
                   name="Оценка сна",
                   showlegend=True,
                   text=person_data['rate'],
                   textposition='outside',
                   base=0,
                   marker_color=clrs
                   )

    fig_rates.add_trace(trace)
    fig_rates.update_layout(title='График оценки сна',
                            font_family='Overpass',
                            xaxis_tickformat='%d %B%Y',
                            font_size=14)
    fig_rates.update_yaxes(categoryorder='array',
                           categoryarray=[i for i in range(11)],
                           range=[0, 10], )
    pio.write_image(fig_rates, r"fig.jpeg")


def on_message(update, context):
    chat = update.effective_chat
    text = update.message.text

    newansw = ['', '', '']
    with sessionmaker(bind=engine).begin() as session:
        Name = update.message.from_user.first_name
        id_n = update.message.from_user.username
        id_t = update.message.from_user.id
        if text == '1533lit':
            context.bot.delete_message(chat_id=chat.id,
                                       message_id=update.message.message_id)
            a1 = Admin(name=Name, name_id=id_n, idt=id_t)
            ms = session.query(Admin).filter(Admin.idt == id_t).first()
            if ms == None:
                session.add(a1)
                context.bot.send_message(chat_id=chat.id, text="Я вас запомнил, новый админ")
        elif text[0] == "-" and session.query(Admin).filter(Admin.idt == id_t).first() != None:
            if text[1:7] == "график":
                idch = text[8::]
                ms = session.query(Users).filter(Users.name_id == idch).first()
                if ms == None:
                    context.bot.send_message(chat_id=chat.id, text="Такого пользователя нет")
                else:
                    onesleep(ms.id)
                    context.bot.send_photo(chat_id=chat.id, photo=open("fig.jpeg", 'rb'))
            elif text[1:7] == "оценка":
                idch = text[8::]
                ms = session.query(Users).filter(Users.name_id == idch).first()
                if ms == None:
                    context.bot.send_message(chat_id=chat.id, text="Такого пользователя нет")
                else:
                    ratesleep(int(ms.id))
                    context.bot.send_photo(chat_id=chat.id, photo=open("fig.jpeg", 'rb'))
    # try:
    s = text

    if s[0] == '#':
        if s[1:5] == 'утро':

            newansw = add(s, newansw)

            today = str(date.today())
            if newansw[0] == '' or newansw[1] == '' or newansw[2] == '':
                raise OSError
            id_n = update.message.from_user.username
            with sessionmaker(bind=engine).begin() as session:
                b1 = Sleep(time_start=newansw[0], time_end=newansw[1], date=today, rate=newansw[2])
                ms = session.query(Users).filter(Users.name_id == id_n).first()
                if ms == None:
                    context.bot.send_message(chat_id=chat.id, text="Введи сначала цель под #цель")
                else:

                    ms.users_shares.append(b1)
                    context.bot.send_message(chat_id=chat.id,
                                             text='ты лег в ' + newansw[0] + ", проснулся в " + newansw[
                                                 1] + ", а оценил на " + newansw[2])
                print("DO")
                session.commit()
            sleep, users = prepare()
            person_data = sleep[sleep['user_id'] == ms.id]
            person_data = person_data.drop_duplicates(subset=['date'])
            person_data = smth(users, person_data, ms.id)
            person_data = prepare2(person_data)
            if pd.Timestamp('now').normalize() in person_data['date'].unique():
                person_current_k = person_data[person_data['date'] == pd.Timestamp('now').normalize()]
                ind = person_current_k.index[0]
                person_current_k['k'] = sleep_k(person_current_k['ttdiff_start'], ind) + sleep_k(
                    person_current_k['ttdiff_end'], ind) + 1
                session.query(Sleep).filter(Sleep.idt == id_t).update({'k': person_current_k['k'][ind] + check_k()})
                session.query(Sleep).filter(Sleep.idt == id_t).update({'points': 15 * person_data['k'][ind]})
        if s[1:7] == 'график':
            id_n = update.message.from_user.username
            with sessionmaker(bind=engine).begin() as session:
                ms = session.query(Users).filter(Users.idt == id_t).first()
                if ms == None:
                    context.bot.send_message(chat_id=chat.id, text="Введи сначала цель под #цель")
                else:
                    onesleep(ms.id)
                    context.bot.send_photo(chat_id=ms.idt, photo=open("fig.jpeg", 'rb'))
                    context.bot.send_message(chat_id=chat.id, text="Проверь лс")
        if s[1:5] == 'цель':
            newansw = add(s, newansw)
            if newansw[0] == '' or newansw[1] == '':
                raise EOFError
            Name = update.message.from_user.first_name
            id_n = update.message.from_user.username
            id_t = update.message.from_user.id
            u1 = Users(name=Name, name_id=id_n, idt=id_t, time_g_start=newansw[0], time_g_end=newansw[1])
            with sessionmaker(bind=engine).begin() as session:
                ms = session.query(Users).filter(Users.name_id == id_n).first()
                if ms == None:
                    session.add(u1)
                    context.bot.send_message(chat_id=chat.id, text="Данные записаны")
                else:

                    session.query(Users).filter(Users.name_id == id_n).update({'time_g_start': newansw[0]})
                    session.query(Users).filter(Users.name_id == id_n).update({'time_g_end': newansw[1]})
                    context.bot.send_message(chat_id=chat.id, text="Данные обновлены")
            session.commit()
        if s[1:7] == 'оценка':
            id_n = update.message.from_user.username
            with sessionmaker(bind=engine).begin() as session:
                ms = session.query(Users).filter(Users.idt == id_t).first()
                if ms == None:
                    context.bot.send_message(chat_id=chat.id, text="Введи сначала цель под #цель")
                else:
                    ratesleep(int(ms.id))
                    context.bot.send_photo(chat_id=ms.idt, photo=open("fig.jpeg", 'rb'))
                    context.bot.send_message(chat_id=chat.id, text="Проверь лс")

    # except:
    #   if s[0:5] == '#утро' or s [0:5]=="#цель":
    #     context.bot.send_message(chat_id=chat.id, text="Ты неправильно ввел данные")
    # if s[0:7]=="#график":
    #    context.bot.send_message(chat_id=Admin.idt, text = "Проблема с графиком")
    # else:
    #   pass


dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", on_start))
dispatcher.add_handler(MessageHandler(Filters.all, on_message))

updater.start_polling()
updater.idle()
