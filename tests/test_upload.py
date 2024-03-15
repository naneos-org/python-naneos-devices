import pandas as pd

from naneos.iotweb import Partector2ProGarageUpload


def _callback_upload(state: bool) -> None:
    print(f"Upload state: {state}")


def test_upload_cs() -> None:
    df = pd.read_pickle("tests/df_upload_test.pkl")
    df = df.iloc[0]
    # print(df.describe())

    # Create a Partector2ProGarageUpload object
    Partector2ProGarageUpload(df, 8448, _callback_upload).start()


if __name__ == "__main__":
    test_upload_cs()
