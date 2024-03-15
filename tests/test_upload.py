import numpy as np
import pandas as pd

from naneos.iotweb import Partector2ProGarageUpload


def _callback_upload(state: bool) -> None:
    print(f"Upload state: {state}")


def print_ser(ser: pd.Series) -> None:
    print(type(ser.name))


def test_upload_cs() -> None:
    df = pd.read_pickle("tests/df_upload_test.pkl").iloc[0:1]
    # set first index to nan
    # df.index = np.nan
    # print(df)
    # print(df.describe())

    df_append = pd.DataFrame(columns=df.columns, index=[np.NaN])
    df = pd.concat([df, df_append])

    # print(df.dtypes)

    # make index int
    df.dropna(inplace=True)
    df.index = df.index.astype(int)

    df.apply(print_ser, axis=1)

    # Create a Partector2ProGarageUpload object
    # Partector2ProGarageUpload(df, 8448, _callback_upload).start()


if __name__ == "__main__":
    test_upload_cs()
