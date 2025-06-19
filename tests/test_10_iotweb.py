# import datetime as dt
# import os

# import pandas as pd

# from naneos.iotweb import download_from_iotweb
# from naneos.iotweb.naneos_upload_thread import NaneosUploadThread


# def test_download_8134() -> None:
#     token: str | None = os.getenv("IOT_GUEST_TOKEN", None)
#     if token is None:
#         raise ValueError("No token found in your environment")

#     # use local timezone for start
#     start = dt.datetime(2025, 4, 1)
#     stop = dt.datetime(2025, 4, 7)
#     serial_number = "8134"
#     name = "iot_guest"

#     df: pd.DataFrame = download_from_iotweb(name, serial_number, start, stop, token)
#     assert len(df) == 206545


# callback_upload_success = {"result": False}


# def callback_upload(ret: bool) -> None:
#     callback_upload_success["result"] = ret


# def test_upload() -> None:
#     data_dir = os.path.join(os.path.dirname(__file__), "data")

#     df_p2 = pd.read_pickle(os.path.join(data_dir, "p2_test_data.pkl"))
#     assert not df_p2.empty, "DataFrame is empty or not loaded correctly"

#     df_p2_pro = pd.read_pickle(os.path.join(data_dir, "p2_pro_test_data.pkl"))
#     assert not df_p2_pro.empty, "DataFrame is empty or not loaded correctly"

#     data = [
#         (int(777), str("P2pro"), df_p2_pro),
#         (int(666), str("P2"), df_p2),
#     ]

#     thread = NaneosUploadThread(data, callback_upload)

#     thread.start()
#     thread.join()

#     assert callback_upload_success["result"], "Upload failed, callback returned False"


# if __name__ == "__main__":
#     # test_download_8134()
#     test_upload()
