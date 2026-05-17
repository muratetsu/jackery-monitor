"""
Acknowledgments:
This code is largely based on the implementation introduced in the following Qiita article by Hsky16:
https://qiita.com/Hsky16/items/c163137265a87186ac39
"""
import json
import os
import random
import requests
import string
import time
import base64
import uuid
import hashlib
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional
from Cryptodome.Cipher import AES, PKCS1_v1_5
from Cryptodome.PublicKey import RSA
from Cryptodome.Util.Padding import pad


class JackeryAPI:
    """
    JackeryAPIクラスの機能は以下の通り:
      1. login: ログイン処理
      2. get_device_list: デバイス一覧の取得
      3. get_device_detail: 指定デバイスの詳細情報の取得
    トークンは token.json に保存し、期限切れ時は自動で再ログインを行う。
    """

    def __init__(self, account: str, password: str, android_id: str = "abcd1234567890ef"):
        """
        :param account: ログイン用アカウント
        :param password: ログイン用パスワード
        :param android_id: UDID生成に使用するAndroid ID相当の文字列
        """
        self.account = account
        self.password = password
        self.android_id = android_id
        self.token_file = Path("token.json")
        self.base_url = "https://iot.jackeryapp.com"

    def _name_uuid_from_bytes_java(self, data: bytes) -> str:
        """
        MD5ハッシュを利用してバージョン3のUUIDを生成し、ダッシュを除去して返す。
        """
        md5_digest = hashlib.md5(data).digest()
        u = uuid.UUID(bytes=md5_digest, version=3)
        return str(u).replace("-", "")

    def _generate_udid(self) -> str:
        """
        UDID生成。
        - 有効なandroid_idの場合、"2" + name_uuid_from_bytes_java(android_id) を返す。
        - 無効な場合、"9" + ランダムUUID（ダッシュ除去）を返す。
        """
        if self.android_id and self.android_id != "9774d56d682e549c":
            return "2" + self._name_uuid_from_bytes_java(self.android_id.encode("utf-8"))
        else:
            random_uuid_str = str(uuid.uuid4()).replace("-", "")
            return "9" + random_uuid_str

    def _encrypt_with_aes(self, plain_text: str, aes_key: bytes) -> str:
        """
        AES暗号化（ECBモード、PKCS5Padding）を行い、Base64エンコードした文字列を返す。
        """
        cipher = AES.new(aes_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))
        return base64.b64encode(encrypted).decode("utf-8")

    def _encrypt_with_rsa(self, data: bytes, public_key_b64: str) -> str:
        """
        RSA暗号化（RSA/ECB/PKCS1Padding）を行い、Base64エンコードした文字列を返す。
        public_key_b64はBase64エンコードされたRSA公開鍵（DER形式）であるため、
        PEM形式に変換してから利用する。
        """
        pub_key_pem = (
                "-----BEGIN PUBLIC KEY-----\n" +
                public_key_b64 +
                "\n-----END PUBLIC KEY-----"
        )
        pub_key = RSA.importKey(pub_key_pem)
        cipher = PKCS1_v1_5.new(pub_key)
        encrypted = cipher.encrypt(data)
        return base64.b64encode(encrypted).decode("utf-8")

    def _load_token(self) -> Optional[str]:
        """
        token.json からトークンを読み込む。
        """
        if self.token_file.is_file():
            try:
                data = json.loads(self.token_file.read_text(encoding="utf-8"))
                return data.get("token")
            except Exception:
                pass
        return None

    def _save_token(self, token: str):
        """
        token.json にトークンを保存する。
        """
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump({"token": token}, f, ensure_ascii=False, indent=2)

    def login(self) -> str:
        """
        ログイン処理を行い、トークンを取得・保存して返す。
        """
        mac_id = self._generate_udid()
        login_bean = {
            "account": self.account,
            "loginType": 2,  # パスワードログイン
            "macId": mac_id,
            "password": self.password,
            "phone": "",
            "registerAppId": "com.hbxn.jackery",
            "verificationCode": ""
        }

        public_key_b64 = (
            "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCVmzgJy/4XolxPnkfu32YtJqYG"
            "FLYqf9/rnVgURJED+8J9J3Pccd6+9L97/+7COZE5OkejsgOkqeLNC9C3r5mhpE4zk"
            "/HStss7Q8/5DqkGD1annQ+eoICo3oi0dITZ0Qll56Dowb8lXi6WHViVDdih/oeUwV"
            "JY89uJNtTWrz7t7QIDAQAB"
        )
        # Jackeryのサーバーは文字コードとして解釈できないバイナリデータを拒否するため、
        # ランダムな16文字の英数字を生成してセッションごとのAES鍵として使用する
        aes_key = ''.join(random.choices(string.ascii_letters + string.digits, k=16)).encode('utf-8')
        login_bean_json = json.dumps(login_bean, ensure_ascii=False)
        aes_encrypt_data = self._encrypt_with_aes(login_bean_json, aes_key)
        rsa_for_aes_key = self._encrypt_with_rsa(aes_key, public_key_b64)

        url = f"{self.base_url}/v1/auth/login"
        params = {
            "aesEncryptData": aes_encrypt_data,
            "rsaForAesKey": rsa_for_aes_key
        }
        # Android版のheadersが不明だったため、iOS版のものを付与する。以下より拝借。
        # https://note.com/kotobuki157/n/n4b977c03f88b?nt=comment_to_4318042
        headers = {
            "app_version": "1.0.5",
            "upload-incomplete": "?0",
            "sys_version": "17.2",
            "platform": "1",
            "upload-draft-interop-version": "3",
            "accept": "*/*",
            "accept-language": "ja-JP",
            "accept-encoding": "br;q=1.0, gzip;q=0.9, deflate;q=0.8",
            "User-Agent": "DxPowerProject/1.0.5 (com.hb.jackery; build:2; iOS 17.2.0) Alamofire/5.8.0",
            "model": "iPad Pro (12.9-inch) (3rd generation)"
        }
        files = {"file": ("", b"", "")}

        try:
            response = requests.post(url, params=params, headers=headers, files=files)
            print("[login] Status Code:", response.status_code)
            print("[login] Response Body:", response.text)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    token = data.get("token", "")
                    if token:
                        self._save_token(token)
                        return token
                    else:
                        raise RuntimeError("No token in login response.")
                else:
                    raise RuntimeError(f"Login failed: {data}")
            else:
                raise RuntimeError(f"HTTP Error: {response.status_code}")
        except Exception as e:
            raise RuntimeError(f"Login request failed: {str(e)}")

    def _ensure_token(self) -> str:
        """
        トークンが未取得または期限切れの場合はlogin()を呼び出して再取得する。
        """
        token = self._load_token()
        if not token:
            token = self.login()
        return token

    def _check_token_expired(self, response_json: dict) -> bool:
        """
        レスポンスからトークン期限切れ（code=10402）かどうか判定する。
        """
        return response_json.get("code") == 10402

    def get_device_list(self) -> dict:
        """
        デバイス一覧を取得する。トークン期限切れの場合は自動で再ログインし再試行する。
        """
        token = self._ensure_token()
        headers = {
            'content-type': 'application/json',
            'accept': '*/*',
            'app_version': '1.0.5',
            'sys_version': '17.2',
            'accept-encoding': 'br;q=1.0, gzip;q=0.9, deflate;q=0.8',
            'accept-language': 'ja-JP',
            'platform': '1',
            'user-agent': 'DxPowerProject/1.0.5 (com.hb.jackery; build:2; iOS 17.2.0) Alamofire/5.8.0',
            'model': 'iPad Pro (12.9-inch) (3rd generation)',
            'token': token
        }
        url = f"{self.base_url}/v1/device/bind/list"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if self._check_token_expired(data):
                print("[get_device_list] Token expired. Re-login...")
                self.login()
                return self.get_device_list()
            else:
                return data
        else:
            raise RuntimeError(f"HTTP Error: {response.status_code}")

    def get_device_detail(self, device_id: str) -> dict:
        """
        指定したデバイスIDの詳細情報を取得する。トークン期限切れの場合は再ログインし再試行する。
        """
        token = self._ensure_token()
        # Android版のheadersが不明だったため、iOS版のものを付与する。以下より拝借。
        # https://note.com/kotobuki157/n/n4b977c03f88b?nt=comment_to_4318042
        headers = {
            'content-type': 'application/json',
            'accept': '*/*',
            'app_version': '1.0.5',
            'sys_version': '17.2',
            'accept-encoding': 'br;q=1.0, gzip;q=0.9, deflate;q=0.8',
            'accept-language': 'ja-JP',
            'platform': '1',
            'user-agent': 'DxPowerProject/1.0.5 (com.hb.jackery; build:2; iOS 17.2.0) Alamofire/5.8.0',
            'model': 'iPad Pro (12.9-inch) (3rd generation)',
            'token': token
        }
        url = f"{self.base_url}/v1/device/property?deviceId={device_id}"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if self._check_token_expired(data):
                print("[get_device_detail] Token expired. Re-login...")
                self.login()
                return self.get_device_detail(device_id)
            else:
                return data
        else:
            raise RuntimeError(f"HTTP Error: {response.status_code}")


if __name__ == "__main__":
    # アカウント情報の読み込み
    config_file = Path("config.json")
    if not config_file.is_file():
        print("エラー: config.json が見つかりません。config.sample.json をコピーして作成してください。")
        exit(1)
        
    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    account = config.get("account")
    password = config.get("password")

    if not account or not password:
        print("エラー: config.json に account または password が設定されていません。")
        exit(1)

    # 1.APIを初期化
    api = JackeryAPI(account=account,password=password)

    # 2. ログインしてトークンを取得
    token = api.login()
    print("Obtained token:", token)

    # 3. デバイス一覧を取得
    device_list = api.get_device_list()
    print("Device List:", device_list)

    # 登録デバイスが存在する場合、最初のデバイスIDを利用
    device_id = device_list["data"][0]["devId"]

    log_dir = Path(__file__).parent  # CSVファイルの保存ディレクトリ
    error_log_filename = log_dir / "errorlog.txt"
    csv_header = [
        "Timestamp", "Battery(%)", "BatteryTemp(C)", "ACInputPower(W)", "InputPower(W)", "InputTime(h)",
        "OutputAC", "OutputDC", "ACOutputVoltage(V)", "OutputPower(W)", "OutputTime(h)",
        "LightMode", "ScreenTimeout", "SuperFastCharge", "ChargeSpeed", "LowPowerSetting",
        "PowerManagement", "AutoSavingTime"
    ]

    POLL_INTERVAL_NORMAL = 60    # 通常のポーリング間隔（秒）
    POLL_INTERVAL_IDLE   = 300   # 入出力電力ともゼロ時のポーリング間隔（秒）

    while True:
        input_power  = None
        output_power = None
        try:
            # 毎ループ開始時に当日のCSVパスを決定（日付をまたいだ際に自動でファイル切り替え）
            csv_path = log_dir / f"jackery_log_{datetime.now().strftime('%Y-%m-%d')}.csv"
            if not csv_path.exists():
                with open(csv_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(csv_header)

            result = api.get_device_detail(device_id)
            device_info = result["data"]["properties"]

            remaining_battery = device_info["rb"]  # バッテリー残量(%)
            battery_temperature = device_info["bt"] / 10.0  # バッテリー温度(℃)
            output_power = device_info["op"]  # AC+DC出力電力(W)
            ac_input_power = device_info["acip"]  # AC入力電力(W)
            input_power = device_info["ip"] # 入力電力(W)
            input_time = device_info["it"] / 10.0  # 充電完了時間(h)
            output_ac = device_info["oac"] == 1  # AC出力のON/OFF
            output_dc = device_info["odc"] == 1  # DC出力のON/OFF
            ac_output_voltage = device_info["acov"] / 10.0  # AC出力電圧(V)
            output_time = device_info["ot"] / 10.0  # 出力可能時間(h)
            light_mode = device_info["lm"]  # ライトモード
            screen_timeout_behavior = device_info["sltb"]  # ディスプレイ設定
            super_fast_charge = device_info["sfc"]  # 緊急充電モード
            charge_speed = device_info["cs"]  # 充電速度設定
            low_power_setting = device_info["lps"]  # パフォーマンス設定
            power_management = device_info["pm"]  # 省エネモード
            auto_saving_time = device_info["ast"]  # 自動オフ時間

            # CSVへの書き出し
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [
                timestamp,
                remaining_battery,
                f"{battery_temperature:.1f}",
                ac_input_power,
                input_power,
                f"{input_time:.1f}",
                output_ac,
                output_dc,
                f"{ac_output_voltage:.1f}",
                output_power,
                f"{output_time:.1f}",
                light_mode,
                screen_timeout_behavior,
                super_fast_charge,
                charge_speed,
                low_power_setting,
                power_management,
                auto_saving_time
            ]

            with open(csv_path, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(row)

            print("----- ポータブル電源の現在の状態 -----")
            print(f"バッテリー残量 (%):          {remaining_battery}%")
            print(f"バッテリー温度 (°C):         {battery_temperature:.1f}℃")
            print()
            print(f"AC入力電力 (W):             {ac_input_power} W")
            print(f"入力電力 (W):               {input_power} W")
            print(f"充電完了時間:                {input_time:.1f} h")
            print()
            print(f"AC出力スイッチ(ON/OFF):      {output_ac}")
            print(f"DC出力スイッチ(ON/OFF):      {output_dc}")
            print(f"AC出力電圧 (V):             {ac_output_voltage:.1f} V")
            print(f"出力電力 (W):               {output_power} W")
            print(f"出力可能時間:                {output_time:.1f} h")
            print()
            print(f"ライトモード:                {light_mode}")
            print(f"ディスプレイ設定:             {screen_timeout_behavior}")
            print()
            print(f"緊急充電モード:              {super_fast_charge}")
            print(f"充電速度設定:                {charge_speed}")
            print(f"パフォーマンス設定:           {low_power_setting}")
            print(f"省エネモード:                {power_management}")
            print(f"自動オフ時間:                {auto_saving_time}")
            print("--------------------------------\n")
        except Exception as e:
            error_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 通信エラーまたは予期せぬエラーが発生しました: {e}"
            print(error_msg)
            with open(error_log_filename, "a", encoding="utf-8") as f_err:
                f_err.write(error_msg + "\n")

        # 入力電力と出力電力が共にゼロの場合はサーバー負荷軽減のため待機時間を延長
        if input_power == 0 and output_power == 0:
            sleep_seconds = POLL_INTERVAL_IDLE
            print(f"入力・出力電力ともにゼロのため、次回取得は {sleep_seconds // 60} 分後です。")
        else:
            sleep_seconds = POLL_INTERVAL_NORMAL
        time.sleep(sleep_seconds)
