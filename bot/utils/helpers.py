import asyncio
import contextlib
import datetime
import functools
import os
import re
import time
import logging
import math
import random
import aiohttp
import ffmpeg
from ffmpeg._run import Error as FFmpegError
import subprocess
from pyrogram import Client, types, StopTransmission
import requests
from bot.config import Config, Script
from database import db
from aiohttp import web
from urllib.parse import urlparse

progress_data = [
    ("▰", "▱"),
    ("▰", "▱"),
    ("▰", "▱"),
    ("▰", "▱"),
    ("▰", "▱"),
    ("▰", "▱"),
    ("▰", "▱"),
]


async def set_commands(app: Client):
    commands = [
        types.BotCommand("start", "Start the bot"),
        types.BotCommand("cancel", "Cancel the downloads"),
        types.BotCommand("admin", "Admin commands"),
    ]
    await app.set_bot_commands(commands)


async def get_admins():
    config = await db.config.get_config("ADMINS")
    return config["value"]


async def add_admin(user_id):
    config = await db.config.get_config("ADMINS")
    if config:
        admins = config["value"]
        if user_id not in admins:
            admins.append(user_id)
            await db.config.update_config("ADMINS", admins)
            return True
    else:
        await db.config.add_config("ADMINS", [user_id])
        return True

    return False


async def remove_admin(user_id):
    config = await db.config.get_config("ADMINS")
    if config:
        admins = config["value"]
        if user_id in admins:
            admins.remove(user_id)
            await db.config.update_config("ADMINS", admins)
            return True
    return False


async def start_webserver():
    routes = web.RouteTableDef()

    @routes.get("/", allow_head=True)
    async def root_route_handler(request):
        res = {
            "status": "running",
        }
        return web.json_response(res)

    async def web_server():
        web_app = web.Application(client_max_size=30000000)
        web_app.add_routes(routes)
        return web_app

    app = web.AppRunner(await web_server())
    await app.setup()
    await web.TCPSite(app, "0.0.0.0", 8000).start()
    logging.info("Web server started")


async def set_commands(app):
    COMMANDS = [
        types.BotCommand("start", "Used to start the bot."),
        types.BotCommand("cancel", "Used to cancel the downloads."),
        types.BotCommand("admin", "Used to access admin commands."),
        types.BotCommand("help", "Used to get help."),
    ]
    await app.set_bot_commands(COMMANDS)


async def add_user(user_id):
    user = await db.users.get_user(user_id)
    if user:
        return
    await db.users.create_user(user_id)
    return True


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        (f"{str(days)}d, " if days else "")
        + (f"{str(hours)}h, " if hours else "")
        + (f"{str(minutes)}m, " if minutes else "")
        + (f"{str(seconds)}s, " if seconds else "")
        + (f"{str(milliseconds)}ms, " if milliseconds else "")
    )
    return tmp[:-2]


def humanbytes(size):
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: " ", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    while size > power:
        size /= power
        n += 1
    return f"{str(round(size, 2))} {Dic_powerN[n]}B"


async def progress_for_pyrogram(
    current, total, start, edit_func, random_string, cancel_markup
):
    if (
        Config.CANCEL_DATA.get(random_string) is True
        or random_string not in Config.CANCEL_DATA
    ):
        raise StopTransmission

    progress_data = [
        ("▰", "▱"),
        ("▰", "▱"),
        ("▰", "▱"),
        ("▰", "▱"),
        ("▰", "▱"),
        ("▰", "▱"),
        ("▰", "▱"),
    ]
    progress_bar = random.choice(progress_data)
    now = time.time()
    diff = now - start
    a, b = progress_bar

    # if total is less than 50mb. then do nothing
    if total < 50000000:
        return

    if round(diff % 25.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        elapsed_time = round(diff) * 1000
        time_to_completion = round((total - current) / speed) * 1000
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_time = TimeFormatter(milliseconds=elapsed_time)
        estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)

        progress = "{0}{1}\n".format(
            "".join([a for _ in range(math.floor(percentage / (100 / 15)))]),
            "".join([b for _ in range(15 - math.floor(percentage / (100 / 15)))]),
        ).strip()

        tmp = Script.PROGRESS_MESSAGE

        tmp = tmp.format(
            percentage=round(percentage, 2),
            progress=progress,
            speed=humanbytes(speed),
            eta=estimated_total_time if estimated_total_time != "" else "0 s",
            finished=humanbytes(current),
            total=humanbytes(total),
        )

        with contextlib.suppress(Exception):
            await edit_func(tmp, reply_markup=cancel_markup)


async def get_video_details(video_path):
    try:
        video_info = ffmpeg.probe(video_path)
    except ffmpeg.Error as e:
        print(e.stderr.decode())
        raise e

    width = video_info["streams"][0]["width"]
    height = video_info["streams"][0]["height"]
    duration = video_info["format"]["duration"]

    return width, height, int(duration.split(".")[0])


async def create_thumbnail(inputpath):
    _, __, duration = await get_video_details(inputpath)
    random_duration = random.randint(1, duration)
    # make timestamp HH:MM:SS
    random_duration = str(datetime.timedelta(seconds=random_duration))

    def random_string(length):
        return "".join(random.choices("0123456789", k=length))

    outputpath = f"downloads/{random_string(10)}.jpg"
    await asyncio_command_exec(
        [
            "ffmpeg",
            "-ss",
            random_duration,
            "-i",
            inputpath,
            "-vframes",
            "1",
            outputpath,
        ]
    )
    if not os.path.exists(outputpath):
        return None
    return outputpath


async def asyncio_command_exec(command_to_exec):
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return stdout, stderr


def check(func):
    """Check if user is admin or not"""

    @functools.wraps(func)
    async def wrapper(client: Client, message):
        chat_id = getattr(message.from_user, "id", None)
        admins = await get_admins()

        if chat_id not in admins:
            # <button> [Owner](t.me/Alonedada143)
            markup = types.InlineKeyboardMarkup(
                [[types.InlineKeyboardButton("Owner", url="https://t.me/Reason_Someone")]]
            )
            return await message.reply_text(
                "You are not allowed to use this bot. If you want to use me first talk to Owner to use me",
                reply_markup=markup,
            )

        banned_users = await db.users.filter_users({"banned": True})
        banned_users = [user["_id"] for user in banned_users]
        if chat_id in banned_users:

            return await message.reply_text("You are banned from using the bot!")

        return await func(client, message)

    return wrapper


async def format_url(url: str, quality: str = "1"):
    # https://drive.google.com/open?id=168NnCzhEfNAF83mBJLcayQfnlG3EhN64
    V = (
        url.replace("file/d/", "uc?export=download&id=")
        .replace("www.youtube-nocookie.com/embed", "youtu.be")
        .replace("?modestbranding=1", "")
        .replace("/view?usp=sharing", "")
        .replace("/open?id=", "/uc?export=download&id=")
    )  # .replace("mpd","m3u8")
    url = V

    if "visionias" in url:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Pragma": "no-cache",
                    "Referer": "http://www.visionias.in/",
                    "Sec-Fetch-Dest": "iframe",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "cross-site",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": "Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36",
                    "sec-ch-ua": '"Chromium";v="107", "Not=A?Brand";v="24"',
                    "sec-ch-ua-mobile": "?1",
                    "sec-ch-ua-platform": '"Android"',
                },
            ) as resp:
                text = await resp.text()
                url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

    elif "videos.classplusapp" in url:
        url = requests.get(
            f"https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}",
            headers={
                "x-access-token": "eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwiZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlvbmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxPPfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0"
            },
        ).json()["url"]

    elif "player.vimeo" in url:
                cmd = f'yt-dlp -f "{ytf}+bestaudio" --no-keep-video --remux-video mp4 "{url}" -o "{name}.%(ext)s"'
        
    elif "m3u8" or "livestream" in url:
                cmd = f'yt-dlp -f "{ytf}" --no-keep-video --remux-video mp4 "{url}" -o "{name}.%(ext)s"'
            
    elif ytf == "0" or "unknown" in out:
                cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4" -N 200'
                
    elif "tencdn.classplusapp" in url:
        headers = {
            "Host": "api.classplusapp.com",
            "x-access-token": "eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwiZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlvbmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxPPfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0",
            "user-agent": "Mobile-Android",
            "app-version": "1.4.37.1",
            "api-version": "18",
            "device-id": "5d0d17ac8b3c9f51",
            "device-details": "2848b866799971ca_2848b8667a33216c_SDK-30",
            "accept-encoding": "gzip",
        }
        params = (("url", f"{url}"),)
        response = requests.get(
            "https://api.classplusapp.com/cams/uploader/video/jw-signed-url",
            headers=headers,
            params=params,
        )
        url = response.json()["url"]
        
    elif "appx1.arvind.eu.org" in url:
        if quality == "1":
            url = url.replace("main.m3u8", "720p.m3u8")
        elif quality == "2":
            url = url.replace("main.m3u8", "480p.m3u8")
        elif quality == "3":
            url = url.replace("main.m3u8", "360p.m3u8")

    elif url.startswith("https://d1d34p8vz63oiq.cloudfront.net/") or url.startswith(
        "https://d1d34p8vz63oiq.cloudfront.net/"
    ):
        """
        Sample Link :- https://d1d34p8vz63oiq.cloudfront.net/8eca5705-a305-4c1d-863f-a5b101c1983a/master.m3u8
        """
        r_code = requests.get(url=url)
        print(r_code)
        if r_code.status_code != 200:
            link = (
                f'https://d3nzo6itypaz07.cloudfront.net/{url.split("/")[-2]}/master.m3u8'
            )
            print(link)
            r_code1 = requests.get(url=link)
            if r_code1.status_code == 200:
                url = link

    elif url.startswith("https://videotest.adda247.com/"):
        if url.split("/")[3] != "demo":
            url = f'https://videotest.adda247.com/demo/{url.split("https://videotest.adda247.com/")[1]}'

    elif not url.startswith("http"):
        splitted = url.split("*")[0]
        splitted1 = url.split("*")[1]
        ACCOUNT_ID = "6206459123001"
        BCOV_POLICY = "BCpkADawqM1474MvKwYlMRZNBPoqkJY-UWm7zE1U769d5r5kqTjG0v8L-THXuVZtdIQJpfMPB37L_VJQxTKeNeLO2Eac_yMywEgyV9GjFDQ2LTiT4FEiHhKAUvdbx9ku6fGnQKSMB8J5uIDd"
        BC_URL = (
            f"https://edge.api.brightcove.com/playback/v1/accounts/{ACCOUNT_ID}/videos"
        )
        BC_HDR = {"BCOV-POLICY": BCOV_POLICY}
        video_response = requests.get(f"{BC_URL}/{splitted}", headers=BC_HDR)
        video = video_response.json()
        # print(video["sources"])
        try:
            video_source = video["sources"][5]
            video_url = video_source["src"]
        except IndexError:
            video_source = video["sources"][1]
            video_url = video_source["src"]
        url = video_url + splitted1

    elif url.endswith("ankul60"):
        host = f"https://{url.split('/')[2]}"
        _id = url.split("/")[-1].split("-")[0]
        print(host)
        r = requests.post(
            f"{host}/route?route=item%2Fliveclasses&id={_id}&response-type=2&fromapp=1&loadall=1&clientView=1&liveFromCDN=1&clientVersion=1.9"
        ).json()
        if None == r["data"]["tr1info"]["primPlaybackUrl"]:
            ytid = r["data"]["tr1info"]["data"]["youtubeId"]
            link = f"https://www.youtube.com/watch?v={ytid}"
        else:
            link = r["data"]["tr1info"]["primPlaybackUrl"]

        if "m3u8" in link:
            url = rout(url=url, m3u8=link)
        elif "youtu" in link:
            url = link

    return url


def rout(url, m3u8):
    rout_link = f'https://{url.split("/")[2]}/?route=common/ajax&mod=liveclasses&ack=getcustompolicysignedcookiecdn&stream={"/".join(m3u8.split("/")[0:-1]).replace("/", "%2F").replace(":", "%3A")}master.m3u8'
    return rout_link


def get_filename_from_headers(url):
    # Send a HEAD request to the URL to get the headers
    response = requests.head(url, allow_redirects=True)

    # Check for the 'Content-Disposition' header
    content_disposition = response.headers.get("Content-Disposition")

    if content_disposition:
        # Extract the filename from the 'Content-Disposition' header
        filename = content_disposition.split("filename=")[1].strip('"')
    else:
        # If no filename in headers, fallback to the URL path
        filename = os.path.basename(urlparse(url).path)

    ext = filename.split(".")[-1].split("?")[0]
    return filename


def format_caption(custom_caption, output_path, url, is_media, file_index, batch_name):
    # file_name, file_size, file_extension, file_url, file_duration = output_path
    if is_media:
        try:
            video_info = ffmpeg.probe(output_path)
        except ffmpeg.Error as e:
            raise e
    else:
        size = os.path.getsize(output_path)
        video_info = {"format": {"size": size, "duration": 0}}

    file_name = output_path.split("/")[-1]
    file_size = video_info["format"]["size"]
    file_extension = file_name.split(".")[-1]
    file_url = url
    file_duration = video_info["format"]["duration"]
    file_duration = int(float(file_duration) * 1000)

    caption = custom_caption
    caption = caption.replace("{file_name}", file_name)
    caption = caption.replace("{file_size}", humanbytes(float(file_size)))
    caption = caption.replace("{file_extension}", file_extension)
    caption = caption.replace("{file_url}", file_url)
    caption = caption.replace("{file_duration}", TimeFormatter(file_duration))
    caption = caption.replace("{file_index}", str(file_index))
    caption = caption.replace("{batch_name}", batch_name)

    return caption


def format_name(name: str, url: str):
    name = name.replace("\n", "").replace("\r", "").replace("\t", "")
    name = name.replace(" ", "_")
    ext = url.split(".")[-1].split("?")[0]

    if len(name) > 64:
        print(f"Name too long: {name}")
        name = name[:64] + "." + ext

    return name


def get_random_thumb():
    if not Config.THUMBNAILS:
        return None
    return random.choice(Config.THUMBNAILS)


def get_random_emoji():
    # get loading emojis
    return random.choice(
        [
            "🐼",
            "🐶",
            "🐅",
            "⚡️",
        ]
    )
