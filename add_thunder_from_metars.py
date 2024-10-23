import argparse
import pandas as pd
import pitot
import readers
from sklearn.neighbors import NearestNeighbors
import numpy as np
from add_weather_from_METARs import FitWeather


def add_thunder(flights,airports,metars,lvar,geo_scale,hour_scale):
    df = flights.copy()#["flight_id"]
    for airport in ["adep","ades"]:
        df= pd.merge(df,airports[["icao_code","latitude_deg","longitude_deg"]],left_on=airport,right_on="icao_code",suffixes=('_adep','_ades'))
    df = df.reset_index()
    postimeMETARs = ("lat","lon","valid")
    mertars = metars.reset_index()
    model = FitWeather(geo_scale=geo_scale,hour_scale=hour_scale).fit(metars,postimeMETARs)
    postime_ades = ("latitude_deg_ades","longitude_deg_ades","arrival_time")
    # postime_adep = ("latitude_deg_adep","longitude_deg_adep","actual_offblock_time")
    res = df[["flight_id"]].set_index("flight_id")
    for radius in [1,2,3,4,5,6]:
        for apt,postime in (("ades",postime_ades),):
            dist,index = model.radius_neighbors(df,postime,radius)
            for wx in ["TS","+TS","VCTS","+VCTS","FG"]:
                l=np.array([metars.iloc[i].wxcodes.str.contains(wx,regex=False).max() for i in index])
                fx =f"thunder_max_{wx.replace('+','p')}_{radius}_{apt}"
                print(fx)
                df[fx]=pd.Series(l).fillna(0.)
                df[fx]=df[fx].astype(np.float64)
                res = res.join(df[["flight_id",fx]].set_index("flight_id"),on="flight_id",how="left")
            # for wx in ["TS","+TS","VCTS","+VCTS"]:
            #     l=np.array([metars.iloc[i].wxcodes.str.contains(wx,regex=False).max() for i in index])
            #     fx =f"thunder_max_{wx.replace('+','p')}_{radius}_{apt}"
            #     print(fx)
            #     df[fx]=pd.Series(l).fillna(0.)
            #     df[fx]=df[fx].astype(np.float64)
            #     res = res.join(df[["flight_id",fx]].set_index("flight_id"),on="flight_id",how="left")
    return res.reset_index()

def main():
    import readers
    parser = argparse.ArgumentParser(
                    prog='add_wind',
                    description='sort points of each trajectory by date, and convert units to SI units, and store good dtype',
    )
    parser.add_argument("-f_in")
    parser.add_argument("-airports")
    parser.add_argument("-metars")
    parser.add_argument("-f_out")
    parser.add_argument("-geo_scale",type=float)
    parser.add_argument("-hour_scale",type=float)
    args = parser.parse_args()
    lvar = ["wxcodes"]
    metars = pd.read_parquet(args.metars)[["lon","lat","valid"]+lvar]
    # print(list(metars))
    # raise Exception
    # tref = metars["valid"].min()
    # metars["hour"]=(metars["valid"]-tref) / np.timedelta64(1, 'h')
    airports = pd.read_parquet(args.airports)
    flights = readers.read_flights(args.f_in)#.head()
    dfadded = add_thunder(flights,airports,metars,lvar,args.geo_scale,args.hour_scale)
    # for airport in ["adep","ades"]:
    #     df= pd.merge(df,airports[["icao_code","latitude_deg","longitude_deg"]],left_on=airport,right_on="icao_code",suffixes=('_adep','_ades'))
    return dfadded.to_parquet(args.f_out,index=False)
if __name__ == '__main__':
    main()