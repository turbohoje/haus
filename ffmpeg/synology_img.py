#!/usr/bin/env python3

import requests
import urllib3
import random
import os

# --- CONFIGURATION ---
NAS_URL = 'https://10.22.14.3:5001'
UN = os.getenv("UN")
PW = os.getenv("PW")
TAG = 'tv'
DOWNLOAD_DIR = '/home/turbohoje/haus/ffmpeg/imgproc/'
DOWNLOAD_CACHE_DIR = '/home/turbohoje/haus/ffmpeg/cache/'
VERIFY_SSL = False  # Set to True if you have a valid cert

import requests
import sys
import shutil
import glob
import pickle
from PIL import Image, ExifTags
import time
import pprint
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_synology_token(nas_url, username, password):
    """
    Logs in to Synology NAS and returns the SynoToken and session ID.
    
    :param nas_url: Base URL of the NAS (e.g., http://192.168.1.100:5000)
    :param username: Synology account username
    :param password: Synology account password
    :return: dict with SynoToken and SID
    """
    login_url = f"{nas_url}/webapi/auth.cgi"

    payload = {
        "api": "SYNO.API.Auth",
        "version": "6",  # version 6 supports Synology Photos
        "method": "login",
        "account": username,
        "passwd": password,
        "session": "FileStation",  # you can use "SurveillanceStation", "DownloadStation", etc., or "FileStation" for generic access
        "format": "cookie"
    }

    try:
        response = requests.get(login_url, params=payload, verify=False)
        response.raise_for_status()
        data = response.json()

        if data["success"]:
            sid = data["data"]["sid"]
            synotoken = response.cookies.get('id') or response.cookies.get('synotoken') or "Not found"
            return {
                "sid": sid,
                "synotoken": synotoken
            }
        else:
            raise Exception(f"Login failed: {data}")
    except Exception as e:
        print(f"Error during login: {e}")
        return None
    

def get_general_tag_id(nas_url, synotoken, sid, tag_name):
    url = f"{nas_url}/webapi/entry.cgi"
    params = {
        "api": "SYNO.Foto.Browse.Tag",
        "method": "list",
        "version": "1",
        "type": "general_tag"
    }
    headers = {
        "X-SYNO-TOKEN": synotoken,
        "Cookie": f"id={sid}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, cookies={"id": sid}, verify=False)
        response.raise_for_status()
        tags = response.json().get("data", {}).get("list", [])
        for tag in tags:
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]
        print(response.json())
        return None
    except Exception as e:
        print(f"Error retrieving tag ID: {e}")
        return None
       
def search_photos_by_tag(nas_url, sid, synotoken, tag=[4]):
    """
    Searches for images with a specific tag in Synology Photos.

    :param nas_url: Base NAS URL
    :param sid: Session ID
    :param synotoken: Synology Token
    :param tag: Tag to filter images
    :return: List of image items with that tag
    """
    search_url = f"{nas_url}/webapi/entry.cgi"

    params = {
        "api": "SYNO.Foto.Browse.Tag",
        "method": "list",
        "version": "3",  # Adjust if necessary; 3 is supported for DSM 7
        "offset": 0,
        "limit": 1000,
        "additional": '["thumbnail","resolution","exif","video_convert","video_meta"]',
        "filter": 'photo',
        "general_tag_id": tag
    }

    headers = {
        "X-SYNO-TOKEN": synotoken,
        "Cookie": f"id={sid}"
    }

    try:
        response = requests.get(search_url, params=params, headers=headers, verify=False, cookies={"id": sid})
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            return data["data"]["list"]
        else:
            print(f"Search failed: {data}")
            return []
    except Exception as e:
        print(f"Error searching photos: {e}")
        return []

def search_photos_by_general_tag(nas_url, sid, synotoken, tag_id):
    url = f"{nas_url}/webapi/entry.cgi"
    params = {
        "api": "SYNO.Foto.Browse.Item",
        "method": "list",
        "version": "4",
        "offset": 0,
        "limit": 500,
        "additional": '["thumbnail", "address"]',
        "general_tag_id": f"{tag_id}"
    }
    headers = {
        "X-SYNO-TOKEN": synotoken,
        "Cookie": f"id={sid}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, cookies={"id": sid}, verify=False)
        response.raise_for_status()
        return response.json().get("data", {}).get("list", [])
    except Exception as e:
        print(f"Error retrieving photos by tag: {e}")
        return []


def download_photo_by_id(nas_url, sid, synotoken, image_id, filename='random.jpg', download_dir=DOWNLOAD_DIR):
    """
    Downloads a Synology Photos image by ID and saves it as 'random.<ext>' in the specified directory.

    :param nas_url: Base NAS URL (e.g., https://192.168.1.100:5001)
    :param sid: Synology session ID
    :param synotoken: Synology token
    :param image_id: The ID of the image to download
    :param filename: Original filename (used to preserve extension)
    :param download_dir: Path to local directory to save image
    :return: Path to saved image or None
    """

    save_path = os.path.join(download_dir, f"{filename}")

    download_url = f"{nas_url}/webapi/entry.cgi"
    params = {
        "api": "SYNO.Foto.Download",
        "method": "download",
        "version": "2",
        "unit_id": f"[{image_id}]",
        "type": "original"
    }
    headers = {
        "X-SYNO-TOKEN": synotoken,
        "Cookie": f"id={sid}"
    }

    try:
        with requests.get(download_url, params=params, headers=headers, cookies={"id": sid}, verify=False, stream=True) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        print(f"Downloaded image to: {save_path}")

        # Check if the image needs rotation based on EXIF orientation
        try:
            img = Image.open(save_path)
            exif = img._getexif()
            if exif is not None:
                #pprint.pprint(exif)

                orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
                if orientation_key and orientation_key in exif:
                    orientation = exif[orientation_key]
                    if orientation == 3:
                        img = img.rotate(180, expand=True)
                        img.save(save_path)
                    elif orientation == 6:
                        img = img.rotate(270, expand=True)
                        img.save(save_path)
                    elif orientation == 8:
                        img = img.rotate(90, expand=True)
                        img.save(save_path)
        except Exception as e:
            print(f"Could not auto-rotate image: {e}")

        return save_path
    except Exception as e:
        print(f"Error downloading image ID {image_id}: {e}")
        return None


def cycle_cached_image():
    pickle_path = os.path.join(DOWNLOAD_DIR, "image_queue.pkl")
    if not os.path.exists(pickle_path):
        print("No pickled image queue found in cache.")
        return
    if os.path.exists(pickle_path):
        with open(pickle_path, "rb") as pf:
            pickled_data = pickle.load(pf)
        images = pickled_data.get("images", [])
        index = pickled_data.get("index", 0)
        if images:
            img = images[index % len(images)]
            img_filename = img.get("filename", f"{img.get('id')}.jpg")
            src_path = os.path.join(DOWNLOAD_CACHE_DIR, img_filename)
            dest_path = os.path.join(DOWNLOAD_DIR, "random.jpg")
            if os.path.exists(src_path):
                shutil.copy(src_path, dest_path)
                print(f"Copied {src_path} to {dest_path}")
                # Advance index and save
                pickled_data["index"] = (index + 1) % len(images)
                with open(pickle_path, "wb") as pf:
                    pickle.dump(pickled_data, pf)
            else:
                print(f"File {src_path} not found in cache.")
        else:
            print("No images in pickled queue.")
    else:
        print("No pickled image queue found in cache.")


def get_exif_by_photo_id(nas_url, sid, synotoken, image_id):
    """
    Retrieves EXIF metadata for a photo from Synology Photos by image ID.

    :param nas_url: Base NAS URL (e.g., https://192.168.1.100:5001)
    :param sid: Synology session ID
    :param synotoken: Synology token
    :param image_id: The ID of the photo
    :return: Dictionary with EXIF metadata or None
    """
    url = f"{nas_url}/webapi/entry.cgi"
    params = {
        "api": "SYNO.Foto.Browse.Item",
        "method": "get",
        "version": "5",
        "id": f"[{image_id}]",
        "additional": '["exif"]'
    }
    headers = {
        "X-SYNO-TOKEN": synotoken,
        "Cookie": f"id={sid}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, cookies={"id": sid}, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            print(data)
            return data["data"].get("additional", {}).get("exif", {})
        else:
            print(f"EXIF retrieval failed: {data}")
            return None
    except Exception as e:
        print(f"Error retrieving EXIF for image ID {image_id}: {e}")
        return None

if __name__ == "__main__":

    download_flag = "--download" in sys.argv

    auth = get_synology_token(NAS_URL, UN, PW)
    if auth:
        print("Login successful!")
        print("SID:", auth["sid"])
        print("SynoToken:", auth["synotoken"])

        #print(get_general_tag_id(NAS_URL, auth["sid"], auth["synotoken"], "tv"))

        images = search_photos_by_general_tag(NAS_URL, auth["sid"], auth["synotoken"], tag_id=4)
        for img in images:
            print(f"- {img.get('filename')} (ID: {img.get('id')})")
        print(f"Found {len(images)} images with tag 'tv'.")

        if download_flag and images:
            pickle_path = os.path.join(DOWNLOAD_DIR, "image_queue.pkl")
            if os.path.exists(pickle_path):
                try:
                    os.remove(pickle_path)
                    print(f"Deleted pickle file: {pickle_path}")
                except Exception as e:
                    print(f"Could not delete pickle file: {e}")

            for f in glob.glob(os.path.join(DOWNLOAD_CACHE_DIR, "*")):
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"Could not remove {f}: {e}")
            for img in images:
                img_id = img.get('id')
                #print("exif")
                #print(get_exif_by_photo_id(NAS_URL, auth["sid"], auth["synotoken"], img_id))
                filename = img.get('filename', f"{img_id}.jpg")
                download_photo_by_id(NAS_URL, auth["sid"], auth["synotoken"], image_id=img_id, filename=filename, download_dir=DOWNLOAD_CACHE_DIR)
            # Shuffle images list
            random.shuffle(images)

            # Prepare data to pickle: images list and index
            pickled_data = {
                "images": images,
                "index": 0
            }

            # Pickle to disk in DOWNLOAD_CACHE_DIR
            pickle_path = os.path.join(DOWNLOAD_DIR, "image_queue.pkl")
            with open(pickle_path, "wb") as pf:
                pickle.dump(pickled_data, pf)

            print(f"Shuffled image list and saved queue to {pickle_path}")
        
        # if images:
        #     random_image = random.choice(images)
        #     image_id = random_image.get('id')
        #     print(f"Randomly selected image ID: {image_id}")
        # else:
        #     print("No images found to select from.")

        # #download_photo_by_id(NAS_URL, auth["sid"], auth["synotoken"], image_id=9441)
        # download_photo_by_id(NAS_URL, auth["sid"], auth["synotoken"], image_id=image_id)

        else:
            cycle_cached_image()
            time.sleep(20)
            cycle_cached_image()
            time.sleep(20)
            cycle_cached_image()
    
