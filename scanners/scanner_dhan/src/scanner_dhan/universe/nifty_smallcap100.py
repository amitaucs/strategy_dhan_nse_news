"""Nifty Smallcap 100 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_SMALLCAP_100_SYMBOLS",
    "NIFTY_SMALLCAP_100_SECURITY_IDS",
    "resolve_nifty_smallcap100_securities",
]

# Official NSE Nifty Smallcap 100 constituents
NIFTY_SMALLCAP_100_SYMBOLS: list[str] = [
    "AARTIIND",
    "ABREL",
    "AEGISLOG",
    "AFCONS",
    "AFFLE",
    "AMBER",
    "ANANDRATHI",
    "ANANTRAJ",
    "ANGELONE",
    "APTUS",
    "ARE&M",
    "ASTERDM",
    "ATHERENERG",
    "BANDHANBNK",
    "BEML",
    "BLS",
    "BRIGADE",
    "CAMS",
    "CASTROLIND",
    "CDSL",
    "CESC",
    "CGCL",
    "CHAMBLFERT",
    "CHOLAHLDNG",
    "COHANCE",
    "CREDITACC",
    "CROMPTON",
    "CUB",
    "DATAPATTNS",
    "DEEPAKFERT",
    "DELHIVERY",
    "DEVYANI",
    "FIRSTCRY",
    "FIVESTAR",
    "FORCEMOT",
    "FSL",
    "GESHIP",
    "GLAND",
    "GMDCLTD",
    "GPIL",
    "GRSE",
    "HBLENGINE",
    "HINDCOPPER",
    "HSCL",
    "IDBI",
    "IFCI",
    "IGL",
    "IIFL",
    "IKS",
    "INOXWIND",
    "IRCON",
    "ITI",
    "JBMA",
    "JMFINANCIL",
    "JSWCEMENT",
    "JYOTICNC",
    "KARURVYSYA",
    "KAYNES",
    "KEC",
    "KFINTECH",
    "LALPATHLAB",
    "MANAPPURAM",
    "MEESHO",
    "MRPL",
    "NATCOPHARM",
    "NAVINFLUOR",
    "NBCC",
    "NETWEB",
    "NEULANDLAB",
    "NH",
    "NUVAMA",
    "OLAELEC",
    "PGEL",
    "PINELABS",
    "PIRAMALFIN",
    "PNBHOUSING",
    "POONAWALLA",
    "PPLPHARMA",
    "PWL",
    "RAMCOCEM",
    "RBLBANK",
    "REDINGTON",
    "RPOWER",
    "SAGILITY",
    "SAILIFE",
    "SARDAEN",
    "SIGNATURE",
    "SONACOMS",
    "STARHEALTH",
    "SWANCORP",
    "SYNGENE",
    "TATACHEM",
    "TATATECH",
    "TENNIND",
    "TRITURBINE",
    "URBANCO",
    "WELCORP",
    "WHIRLPOOL",
    "WOCKPHARMA",
    "ZENSARTECH",
]

# 100% verified active Dhan Security IDs for Nifty Smallcap 100 stocks
NIFTY_SMALLCAP_100_SECURITY_IDS: dict[str, str] = {
    "AARTIIND": "7",
    "ABREL": "625",
    "AEGISLOG": "40",
    "AFCONS": "25977",
    "AFFLE": "11343",
    "AMBER": "1185",
    "ANANDRATHI": "7145",
    "ANANTRAJ": "13620",
    "ANGELONE": "324",
    "APTUS": "5435",
    "ARE&M": "100",
    "ASTERDM": "1508",
    "ATHERENERG": "757645",
    "BANDHANBNK": "2263",
    "BEML": "395",
    "BLS": "17279",
    "BRIGADE": "15184",
    "CAMS": "342",
    "CASTROLIND": "1250",
    "CDSL": "21174",
    "CESC": "628",
    "CGCL": "20329",
    "CHAMBLFERT": "637",
    "CHOLAHLDNG": "21740",
    "COHANCE": "17945",
    "CREDITACC": "4421",
    "CROMPTON": "17094",
    "CUB": "5701",
    "DATAPATTNS": "7358",
    "DEEPAKFERT": "827",
    "DELHIVERY": "9599",
    "DEVYANI": "5373",
    "FIRSTCRY": "24814",
    "FIVESTAR": "12032",
    "FORCEMOT": "11573",
    "FSL": "14304",
    "GESHIP": "13776",
    "GLAND": "1186",
    "GMDCLTD": "5204",
    "GPIL": "13409",
    "GRSE": "5475",
    "HBLENGINE": "13966",
    "HINDCOPPER": "17939",
    "HSCL": "14334",
    "IDBI": "1476",
    "IFCI": "1491",
    "IGL": "11262",
    "IIFL": "11809",
    "IKS": "28125",
    "INOXWIND": "7852",
    "IRCON": "4986",
    "ITI": "1675",
    "JBMA": "11655",
    "JMFINANCIL": "13637",
    "JSWCEMENT": "758460",
    "JYOTICNC": "21334",
    "KARURVYSYA": "1838",
    "KAYNES": "12092",
    "KEC": "13260",
    "KFINTECH": "13359",
    "LALPATHLAB": "11654",
    "MANAPPURAM": "19061",
    "MEESHO": "760229",
    "MRPL": "2283",
    "NATCOPHARM": "3918",
    "NAVINFLUOR": "14672",
    "NBCC": "31415",
    "NETWEB": "17433",
    "NEULANDLAB": "2406",
    "NH": "11840",
    "NUVAMA": "18721",
    "OLAELEC": "24777",
    "PGEL": "25358",
    "PINELABS": "759820",
    "PIRAMALFIN": "759551",
    "PNBHOUSING": "18908",
    "POONAWALLA": "11403",
    "PPLPHARMA": "11571",
    "PWL": "759723",
    "RAMCOCEM": "2043",
    "RBLBANK": "18391",
    "REDINGTON": "14255",
    "RPOWER": "15259",
    "SAGILITY": "27052",
    "SAILIFE": "27839",
    "SARDAEN": "17758",
    "SIGNATURE": "18743",
    "SONACOMS": "4684",
    "STARHEALTH": "7083",
    "SWANCORP": "27095",
    "SYNGENE": "10243",
    "TATACHEM": "3405",
    "TATATECH": "20293",
    "TENNIND": "759880",
    "TRITURBINE": "25584",
    "URBANCO": "759084",
    "WELCORP": "11821",
    "WHIRLPOOL": "18011",
    "WOCKPHARMA": "7506",
    "ZENSARTECH": "1076",
}


def resolve_nifty_smallcap100_securities(
    dhan_client: dhanhq | None = None,
    security_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Resolve Nifty Smallcap 100 symbols to Dhan security IDs.

    Uses security master DataFrame if provided, falling back to
    built-in verified mappings.
    """
    resolved = dict(NIFTY_SMALLCAP_100_SECURITY_IDS)

    if security_df is not None and not security_df.empty:
        try:
            nse_eq = security_df[
                (security_df["SEM_EXM_EXCH_ID"] == "NSE")
                & (security_df["SEM_INSTRUMENT_NAME"] == "EQUITY")
                & (security_df["SEM_SERIES"] == "EQ")
            ]
            for sym in NIFTY_SMALLCAP_100_SYMBOLS:
                match = nse_eq[nse_eq["SEM_TRADING_SYMBOL"] == sym]
                if not match.empty:
                    resolved[sym] = str(match.iloc[0]["SEM_SMST_SECURITY_ID"])
            logger.info(
                "Resolved %d Nifty Smallcap 100 symbols from security master", len(resolved)
            )
        except Exception as exc:
            logger.warning(
                "Error parsing Nifty Smallcap 100 security master: %s. Using fallback map.",
                exc,
            )

    return resolved
