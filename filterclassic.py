from traffic.algorithms import filters
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,  # for python 3.8 and impunity
    Generic,
    Optional,
    Protocol,
    Type,
    TypedDict,
    TypeVar,
    cast,
)

def checktime(df):
    ''' check that the sequence of datetimes in timestamp are increasing '''
    t = df.timestamp.values
    assert (t[1:]>t[:-1]).all()

def isvar(v):
    ''' test if a measurment @v is constant'''
    isnotnan = ~np.isnan(v)
    diffnotnan = np.logical_and(isnotnan[1:],isnotnan[:-1])
    diff = v[1:] != v[:-1]
    return np.logical_and(diff,diffnotnan)


class FilterCstLatLon(filters.FilterBase):
    ''' filter out measurments where latitude and longitude are constant'''
    def apply(self,df):
        # print(type(df.altitude))
        df = df.copy()
        alt = df.altitude.to_numpy()#values
        lat = df.latitude.to_numpy()#values
        lon = df.longitude.to_numpy()#values
        isupdated = np.zeros(alt.shape, dtype=bool)
        isupdated[1:] = np.logical_or(isvar(lat),isvar(lon))
        df.loc[np.logical_not(isupdated),["latitude","longitude"]]=np.nan
        return df

def compute_holes(t,inans):
    '''
    Compute minimum time difference: dt[i]=min(t[i]-t[i-1],t[i+1]-t[i])
    The trick is that the times @t at index @inans are ignored here,
    so t[i+1] is actually the next valid time t and the same is true for t[i-1]
    '''
    tnan = t.copy()
    tnan[inans] = np.nan
    tf = pd.DataFrame({"tf":tnan}, dtype=np.float64).ffill().values[:,0]
    tb = pd.DataFrame({"tb":tnan}, dtype=np.float64).bfill().values[:,0]
    dt = 10000. * np.ones(tnan.shape[0],dtype=np.float64)
    dt[:-1] = np.minimum(dt[:-1],tb[1:]-tnan[:-1])
    dt[1:] = np.minimum(dt[1:],tnan[1:]-tf[:-1])
    return dt

class FilterIsolated(filters.FilterBase):
    '''
    Based on compute_holes, discard measurements that are separated by at least 20 seconds  from any other measurement
    '''
    def apply(self,df):
        df = df.copy()
        lvar = [x for x in list(df) if x not in ["timestamp","icao24","flight_id"]]
        df["t"] = ((df.timestamp - df.timestamp.iloc[0]) / pd.to_timedelta(1, unit="s")).values.astype(np.float64)
        for v in lvar:
            dt = compute_holes(df["t"],np.isnan(df[v].values))
            df[v] = df[v].mask(dt > 20)
            df[v] = df[v].mask(np.isnan(dt))
        return df.drop(columns=["t"])



class FilterCstPosition(filters.FilterBase):
    ''' filter out measurments where altitude, latitude and longitude are constant'''
    def apply(self,df):
        df = df.copy()
        if df.shape[0]<=1:
            return df
        alt = df.altitude.to_numpy()
        lat = df.latitude.to_numpy()
        lon = df.longitude.to_numpy()
        isupdated = np.zeros(alt.shape,dtype=bool)#False
        isupdated[1:] = np.logical_or(isvar(alt),isvar(lat))
        isupdated[1:] = np.logical_or(isupdated[1:],isvar(lon))
        df.loc[np.logical_not(isupdated),["latitude","longitude","altitude"]]=np.nan
        return df


class FilterCstSpeed(filters.FilterBase):
    ''' filter out measurments where vertical_rate, track and groundspeed are constant'''
    def apply(self,df):
        df = df.copy()
        if df.shape[0]<=1:
            return df
        vrate = df.vertical_rate.to_numpy()
        track = df.track.to_numpy()
        gs = df.groundspeed.to_numpy()
        isupdated = np.zeros(vrate.shape,dtype=bool)
        isupdated[1:] = np.logical_or(isvar(vrate),isvar(gs))
        isupdated[1:] = np.logical_or(isupdated[1:],isvar(track))
        df.loc[np.logical_not(isupdated),["vertical_rate","track","groundspeed"]]=np.nan
        return df


class DerivativeParams(TypedDict):
    first: float  # threshold for 1st derivative
    second: float  # threshold for 2nd derivative


class MyFilterDerivative(filters.FilterBase):
    """Filter based on the 1st and 2nd derivatives of parameters

    The method computes the absolute value of the 1st and 2nd derivatives
    of the parameters. If the value of the derivatives is above the defined
    threshold values, the datapoint is removed
    Idea from FilterDerivative in Traffic but somewhat different:
    -actual time are used to compute time differences
    -use the actual 2nd derivative with no absolute value
    -the discarding mechanism is also different
    """

    # default parameter values
    # default: ClassVar[dict[str, DerivativeParams]] = dict(
    #     altitude=dict(first=200, second=50),
    #     geoaltitude=dict(first=200, second=150),
    #     vertical_rate=dict(first=1500, second=1000),
    #     groundspeed=dict(first=15, second=12),
    #     track=dict(first=12, second=10),
    #     latitude=dict(first=0.01, second=0.06),
    #     longitude=dict(first=0.01, second=0.06),
    # )
    default: ClassVar[dict[str, DerivativeParams]] = dict(
        altitude=dict(first=200, second=50),
        geoaltitude=dict(first=200, second=150),
        vertical_rate=dict(first=1500, second=1000),
        groundspeed=dict(first=12, second=10),
        track=dict(first=12, second=10),
        latitude=dict(first=0.01, second=0.06),
        longitude=dict(first=0.01, second=0.06),
    )

    def __init__(
        self, time_column: str = "timestamp", **kwargs: DerivativeParams
    ) -> None:
        """

        :param time_column: the name of the time column (default: "timestamp")

        :param kwargs: each keyword argument has the name of a feature.
            the value must be a dictionary with the following keys:
            - first: threshold value for the first derivative
            - second: threshold value for the second derivative

        """
        self.columns = {**self.default, **kwargs}
        self.time_column = time_column

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.shape[0]<=2:
            return data
        for column, params in self.columns.items():
            if column not in data.columns:
                continue
            nanmask = np.isnan(data[column].values)
            index = data.index[np.logical_not(nanmask)]
            val = data[column].values[np.logical_not(nanmask)]
            timediff = data.loc[np.logical_not(nanmask),self.time_column].diff().dt.total_seconds().values[1:]
            if column == "track":
                val = np.unwrap(val,period=360)
            diff1val = val[1:]-val[:-1]
            diff1 = np.abs(diff1val)
            diff2 =np.abs(diff1val[1:]-diff1val[:-1])

            deriv1 = diff1 / timediff
            deriv2 = 2 * diff2 / (timediff[1:]+timediff[:-1])
            spikea = deriv2 >= params["second"]
            killa = np.zeros(val.shape[0])
            killa[:-2]+=spikea
            killa[1:-1]+=spikea
            killa[2:]+=spikea
            spikev = deriv1 >= params["first"]
            killv = np.zeros(val.shape[0])
            killv[:-1]+=spikev
            killv[1:]+=spikev
            data.loc[index[np.logical_or(killa>=2,killv>=2)], column] = np.nan

        return data
