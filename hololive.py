import discord
import asyncio
import requests
from datetime import datetime, timedelta
from discord.ext import tasks
import copy
import re
import json
from bs4 import BeautifulSoup
import os
import time
import unicodedata
import traceback

DM_USER_ID = 123456789 #errorlogとかを送信するuser id
CHANNEL_ID_SOON = 123456789 # 配信の予定を通知するチャンネル
CHANNEL_ID_NOW = 123456789 # 配信が始まったら通知するチャンネル
intents = discord.Intents.default()
intents.typing = False
intents.presences = False
client = discord.Client(intents=intents)
dateGroupList_prev = None
sent_soon = set()
sent_now = set()
sent_soon_ids = {} 
sent_now_ids = {}  
news_list = []

async def safe_send(channel, embed):
    while True:
        try:
            message = await channel.send(embed=embed)
            return message
        except Exception as e:
            print(f"Error occurred: {e}")
            dm_user = await client.fetch_user(DM_USER_ID)
            await dm_user.send(f"Error occurred: {e}")
            await asyncio.sleep(10)

async def send_error_message(error_message):
    dm_user = await client.fetch_user(DM_USER_ID)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_with_timestamp = f"{timestamp} | {error_message}"
    await dm_user.send(error_with_timestamp)

async def check_schedule():
    global dateGroupList_prev, sent_soon, sent_now, sent_soon_ids, sent_now_ids
    while True:
        try:
            roles = {}
            if os.path.exists('roles.json'):
                try:
                    with open('roles.json', 'r') as f:
                        roles.update(json.load(f))
                except json.JSONDecodeError:
                    pass

            response = requests.get('https://schedule.hololive.tv/api/list/7')
            print("getting.....")
            data = response.json()
            dateGroupList = data['dateGroupList']
            if dateGroupList_prev is not None:
                for dateGroup in sorted(dateGroupList, key=lambda x: x['datetime']):
                    videoList = dateGroup['videoList']
                    for video in sorted(videoList, key=lambda x: x['datetime']):
                        broadcast_time = datetime.strptime(video['datetime'], '%Y/%m/%d %H:%M:%S')
                        if broadcast_time > datetime.now() and not video['isLive'] and video['url'] not in sent_soon:
                            embed = discord.Embed(title=video['title'], url=video['url'], color=0x808080)
                            embed.set_author(name=video['name'], icon_url=video['talent']['iconImageUrl'])
                            embed.set_thumbnail(url=video['thumbnail'])
                            if video['collaboTalents']:
                                collab_names = ' | '.join([collabo['name'] for collabo in video['collaboTalents']])
                                embed.add_field(name='Collab', value=collab_names, inline=False)
                            embed.add_field(name='Status', value=f'Live soon... ({broadcast_time.strftime("%m/%d %H:%M")})', inline=False)
                            sent_soon.add(video['url'])
                            message = await safe_send(client.get_channel(CHANNEL_ID_SOON), embed)
                            if video['url'] not in sent_soon_ids:
                                sent_soon_ids[video['url']] = []
                            sent_soon_ids[video['url']].append(message.id)
                            await asyncio.sleep(0.2)
                        elif video['isLive'] and (video['url'] not in sent_now or (video['url'] in sent_soon and video['url'] not in sent_now)):
                            video_name_lower = unicodedata.normalize('NFKC', video['name'].lower().replace(" ", ""))
                            name_roles = []
                            for role_name in roles:
                                role_name_lower = unicodedata.normalize('NFKC', role_name.lower().replace(" ", ""))
                                if role_name_lower in video_name_lower:
                                    role_id = roles[role_name]
                                    if isinstance(role_id, list):
                                        name_roles.extend([f'<@&{id}>' for id in role_id])
                                    else:
                                        name_roles.append(f'<@&{role_id}>')
                            if name_roles:
                                await client.get_channel(CHANNEL_ID_NOW).send(' '.join(name_roles))
                            collabo_roles = []
                            for collabo in video['collaboTalents']:
                                collabo_name_lower = unicodedata.normalize('NFKC', collabo['name'].lower().replace(" ", ""))
                                for role_name in roles:
                                    role_name_lower = unicodedata.normalize('NFKC', role_name.lower().replace(" ", ""))
                                    if role_name_lower in collabo_name_lower:
                                        role_id = roles[role_name]
                                        if isinstance(role_id, list):
                                            collabo_roles.extend([f'<@&{id}>' for id in role_id])
                                        else:
                                            collabo_roles.append(f'<@&{role_id}>')
                            if collabo_roles:
                                await client.get_channel(CHANNEL_ID_NOW).send(' '.join(collabo_roles))
                            embed = discord.Embed(title=video['title'], url=video['url'], color=0xFF0000)
                            embed.set_author(name=video['name'], icon_url=video['talent']['iconImageUrl'])
                            embed.set_thumbnail(url=video['thumbnail'])
                            if video['collaboTalents']:
                                collab_names = ' | '.join([collabo['name'] for collabo in video['collaboTalents']])
                                embed.add_field(name='Collab', value=collab_names, inline=False)
                            embed.add_field(name='Status', value='Live now!!!', inline=False)
                            message = await safe_send(client.get_channel(CHANNEL_ID_NOW), embed)
                            if video['url'] not in sent_now_ids:
                                sent_now_ids[video['url']] = []
                            sent_now_ids[video['url']].append(message.id)
                            sent_now.add(video['url'])
                            await asyncio.sleep(0.2)

            for url in list(sent_soon):
                if url in sent_now:
                    if url in sent_soon_ids:
                        message_ids = sent_soon_ids[url]
                        for message_id in message_ids:
                            channel = client.get_channel(CHANNEL_ID_SOON)
                            try:
                                message = await channel.fetch_message(message_id)
                                await message.delete()
                                message_ids.remove(message_id)
                            except discord.NotFound:
                                pass
                        if not message_ids:
                            del sent_soon_ids[url]
                    sent_soon.remove(url)

            for url in list(sent_now):
                if url in dateGroupList_prev and not dateGroupList_prev[url]['isLive'] and datetime.strptime(dateGroupList_prev[url]['datetime'], '%Y/%m/%d %H:%M:%S') < datetime.now():
                    if url in sent_now_ids:
                        message_ids = sent_now_ids[url]
                        for message_id in message_ids:
                            channel = client.get_channel(CHANNEL_ID_NOW)
                            try:
                                message = await channel.fetch_message(message_id)
                                await message.delete()
                                message_ids.remove(message_id)
                            except discord.NotFound:
                                pass
                        if not message_ids:
                            del sent_now_ids[url]
                    sent_now.remove(url)

            dateGroupList_prev = copy.deepcopy(dateGroupList)
            print("wait 5s")
            await asyncio.sleep(5)
            
        except requests.exceptions.RequestException as e:
            error_message = f"Request failed in check_schedule(): {e}"
            print(error_message)
            await send_error_message(error_message)
            await asyncio.sleep(10)
            
        except discord.HTTPException as e:
            error_message = f"Discord API request failed in check_schedule(): {e}"
            print(error_message)
            await send_error_message(error_message)
            await asyncio.sleep(10)

        except Exception as e:
            error_message = f"Unexpected error in check_schedule(): {e}\n{traceback.format_exc()}"
            print(error_message)
            await send_error_message(error_message)
            await asyncio.sleep(10)
        
@tasks.loop(minutes=1)
async def change_status():
    global news_list
    try:
        if not news_list:
            news_list = await get_news()
        news = news_list.pop(0)
        await client.change_presence(activity=discord.Game(name=news))
    except Exception as e:
        error_message = f"Unexpected error in change_status(): {e}\n{traceback.format_exc()}"
        print(error_message)
        await send_error_message(error_message)
        await asyncio.sleep(10)

@tasks.loop(hours=4)
async def get_news():
    try:
        url = "https://hololivepro.com/news/"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        news_items = soup.find_all('a', class_='news_li')[:5]
        news_list = []
        for i, news in enumerate(news_items):
            date = news.find('p', class_='date').text
            title = news.find('h2', class_='tit').text
            news_list.append(f'{date} {title} {"(最新)" if i == 0 else ""}')
        return news_list

    except Exception as e:
        error_message = f"Unexpected error in get_news(): {e}\n{traceback.format_exc()}"
        print(error_message)
        await send_error_message(error_message)
        await asyncio.sleep(10)

@client.event
async def on_ready():
    try:
        print('Bot is ready.')
        change_status.start()
        client.loop.create_task(check_schedule())

    except Exception as e:
        error_message = f"Unexpected error in on_ready(): {e}\n{traceback.format_exc()}"
        print(error_message)
        await send_error_message(error_message)
        await asyncio.sleep(10)

client.run('token')
