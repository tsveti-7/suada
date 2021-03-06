# Stoyan Pisov
# Tsvetelina Ivanova

# Faculty of Physics, Sofia University "St. Kliment Ohridski"
# 2017-2019

# Aim of the python scripts in this project: to export the data from
# the WRF model stored in netCDF format to a SUADA database
# (in NWP 1D and 3D tables).

# http://suada.phys.uni-sofia.bg/
# The Sofia University Data Archive (SUADA) serves
# as a regional database for atmospheric parameters,
# specifically for Integrated Water Vapour (IWV),
# derived using the Global Navigation Satellite Systems (GNSS)
# Meteorology method.

import sys, getopt
import glob
from tzlocal import get_localzone
from dateutil import parser
import datetime
from netCDF4 import Dataset as netcdf
import MySQLdb
import databaseconfig as cfg
import numpy as np
import wrf


# Define global variables:
t_kelvin = 273.15


# Define a procedure that selects the stations'
# ID, Name, Longitude, Latitude, Altitude
# from the SUADA information tables:
def getstations(cur, source_name, country, instrument_name):
	stations=[]
	try:
		cur.execute("select st.ID, \
			st.Name, \
			crd.Longitude, \
			crd.Latitude, \
			crd.Altitude, \
			sen.ID, \
			st.Country \
			from SENSOR as sen left join SOURCE as so ON so.ID = sen.SourceID \
			left join STATION as st ON st.ID = sen.StationID \
			left join COORDINATE as crd ON crd.STationID = st.ID \
			left join INSTRUMENT as instr ON instr.ID = crd.InstrumentID \
			WHERE so.Name = %(source_name)s \
			AND instr.Name = %(instrument_name)s",
			{
				'source_name' : source_name,
				'instrument_name' : instrument_name
			})
		rows =  cur.fetchall()

		if len(rows):
			for row in rows:
				stations.append({'id':row[0],
					'name':row[1],
					'long':row[2],
					'latt':row[3],
					'alt':row[4],
					'senid':row[5],
					'country':row[6]})
	except Exception as e:
		print('Error at getstations: {}'.format(e))

	return stations


# Define a procedure that lists files containing data
# in the selected by the user base directory and prefix:
def listfiles(basedir, prefix):
	files = []
	try:
		for file in sorted(glob.glob(basedir+'/'+prefix+"*")):
			files.append(file)
	except Exception as e:
		print('Exception reading basefolder {} {}'.format(basedir,e))
	return files


# Define a procedure that takes source_name as
# an argument and returns source_id as a result, which is
# later used when inserting into 1D and 3D databases:
def get_source_id(cur, source_name):
	source_id = -1
	try:
		cur.execute("SELECT ID FROM SOURCE WHERE Name = %(source_name)s", {'source_name' : source_name})
		rows = cur.fetchall()
		if len(rows):
			for row in rows:
				source_id = row[0]
	except Exception as e:
		print('Error at get_source_id: {}'.format(e))
	finally:
		return source_id


# Define a procedure that takes the country
# (that the user specified when running the script)
# as an argument and returns the station names
# in this country as a result:
def get_station_name(cur, country):
	name = -1
	try:
		if not country:
			cur.execute("SELECT Name FROM STATION")
		else:
			cur.execute("SELECT Name FROM STATION WHERE Country = %(country)s", {'country' : country})
			rows = cur.fetchall()
			if len(rows):
				for row in rows:
					name = row[0]
	except Exception as e:
		print('Error at get_station_name: {}'.format(e))
	finally:
		return name




# Define a procedure process_station that inserts model data 
# for each station into the SUADA database. 
# It is similar to the next procedure process_station_tro that 
# accumulates data for the troposinex txt format into a dictionary.
# If you change one of these two procedures, 
# you should also change the other accordingly.
def process_station(db, cur, station, ncfile, date):
	result = True
	try:
		stationName = station['name']
		stationId = station['id']
		sensorId = station['senid']
                sourceId = station['source_id']
		x0 = station['long']
		y0 = station['latt']
		z0 = station['alt']
		i0 = station['i0']
		j0 = station['j0']
		print 'Station: ', station['name'], ' ID: ', station['id'], ' sensorId: ', sensorId
		
		# 1D FIELDS:
		# T2 [K] - temperature on 2m height:
		T2 = ncfile.variables['T2'][0]
		# Pressure, [Pa]:
		Pressure = ncfile.variables['PSFC'][0]
		# PBLH, [m] - planatary boundary layer height:
		PBLH = ncfile.variables['PBLH'][0]
		# HGT, [m] - 1D height above sea level:
		HGT = ncfile.variables['HGT'][0]
		# The following 4 fields are in [mm]:
		RAINNC = ncfile.variables['RAINNC'][0]
		SNOWNC = ncfile.variables['SNOWNC'][0]
		GRAUPELNC = ncfile.variables['GRAUPELNC'][0]
		HAILNC = ncfile.variables['HAILNC'][0]
		# Precipitation [mm]:
		Precipitation = RAINNC + SNOWNC + GRAUPELNC + HAILNC

		# 3D FIELDS:
		# T, [K] - temperature:
		T = ncfile.variables['T'][0]
		# P, [Pa] - perturbation pressure:
		P = ncfile.variables['P'][0]
		# PB, [Pa] - base state pressure:
		PB = ncfile.variables['PB'][0]
		# PHB [m] - base state geopotential height:
		PHB = ncfile.variables['PHB'][0]
		# PH [m] - perturbation geopotential height:
		PH = ncfile.variables['PH'][0]
		# QVAPOR [kg/kg] - water vapour mixing ratio:
		QVAPOR = ncfile.variables['QVAPOR'][0]

		# Import 1D fields
		# press, [hPa]:
		press = Pressure[i0][j0]/100.
		# height, [m]:
		heigth = HGT[i0][j0]
		# Calculation of zenith hydrostatic delay (zhd):
		zhd = (0.0022768*(float(press)))/(1.-0.00266*np.cos(2*(float(z0))*(3.1416/180.))-(0.00028*(float(heigth))/1000.))
		pblh = PBLH[i0][j0]
		# temp, [C]:
		temp = T2[i0][j0]-t_kelvin
		# rain, [mm]:
		rain = Precipitation[i0][j0]

		print('Name: {0} [{1}, {2}, {3}] -> [Temperarture [C]: {4}, Pressure [hPa]: {5}, Rain [mm]: {6}, PBL HEIGHT [m]: {7}, Zenit Heigth Delay [x]: {8}] '
			.format(station['name'],
			x0,
			y0,
			z0,
			temp,
			press,
			rain,
			pblh,
			zhd))

		# SQL commands that insert values
		# of parameters in the tables.
		# If there is a dublicate, the existing fileds
		# are updated.
		# 1D data insertion:
		# add additionaly wind and 1d mixing ratio
		cur.execute ( "insert into NWP_IN_1D (Datetime, \
			Temperature, \
			Pressure, \
			Altitude, \
			SensorID, \
			Latitude, \
			Longitude, \
			ZHD, \
			PBL, \
			Precipitation)\
			values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on duplicate key update\
			Temperature = %s,\
			Pressure = %s,\
			Altitude = %s,\
			Latitude = %s,\
			Longitude = %s,\
			ZHD = %s,\
			PBL = %s,\
			Precipitation = %s", [date,
			temp,
			press,
			heigth,
			sensorId,
			y0,
			x0,
			zhd,
			pblh,
			rain,
			temp,
			press,
			heigth,
			y0,
			x0,
			zhd,
			pblh,
			rain])
	
		# 3D data insertion:
		bottom_top = len(T)
		# First, calculation of tk:
		# Rd, Cp, Rd_Cp are used for 3D calculation of
		# tk (absolute temperature [K], and then
		# it's converted to [C]):
		Rd  = 287.0
		Cp  = 7.0 * Rd / 2.0
		Rd_Cp  = Rd / Cp # dimensionless
		Rv = 461.51
		# The following Tm and k1 are used for calculation of ZWD and ZTD later:
		# Tm, [K] - weighted temperature mean:
		Tm = 70.2 + 0.72 * T2[i0][j0]
		k1 = (10**6) / ( Rv*(((3.766 * 10**5)/Tm) + 22.) )

		IWV = 0.
		for k in range(0, bottom_top):
			# temperature in [K]:
			theta = T[k][i0][j0] + 300.
			# Press3d = Pair/100.0 [hPa]
			Pair = (P[k][i0][j0] + PB[k][i0][j0])/100.
			# For tk, (... - t_kelvin) converts T to Celsius.
			# (100.*Pair) is again in [Pa], because
			# in the formula for tk in should be in [Pa].
			tk = theta * ((100.*Pair/100000.)**(Rd_Cp)) - t_kelvin
			# QV, [g/kg] - water vapour mixing ratio:
			QV = QVAPOR[k][i0][j0]*1000.
			# Height, [m]:
			hgth = (PH[k][i0][j0] + PHB[k][i0][j0])/9.81

			# IWV calculations:
			# (equations from modelf.m)
			if k <= 41:
				# Compute specific humidity q1 and q2 from mixing ratio QVAPOR*1000. in [g/kg]:
				q1 =  (QVAPOR[k][i0][j0] * 1000.) / ( (QVAPOR[k][i0][j0] * 1000.) + 1. )
				q2 =  (QVAPOR[k+1][i0][j0] * 1000.) / ( (QVAPOR[k+1][i0][j0] * 1000.) + 1. )

				# Compute water vapour partial pressure with model pressure = (P+PB)/100. in [hPa]:
				# PP = (P[k][i0][j0]+PB[k][i0][j0])
				e_k   = ( ((P[k][i0][j0]+PB[k][i0][j0]) / 100.)   * q1 ) / ( 0.622 + ( 0.378 * q1 ))
				e_kp1 = ( ((P[k+1][i0][j0]+PB[k+1][i0][j0]) / 100.) * q2 ) / ( 0.622 + ( 0.378 * q2 ))

				# Compute water vapour density with T [K]
				# T is perturbation potential temerature TT=T+300. Total Potential temperature [K]
				# Model level temrature is computed TT = T * ( ((P+PB)/100000.) ^ (2/7)) [K]
				# TT = (T[k][i0][j0] + 300.) * (( (P[k][i0][j0]+PB[k][i0][j0])/100000. )**(2./7.))
				# NB to compute the temerature from potential temprature pressure is in [Pa]

				ro_k   = e_k   / ( Rv * ( (T[k][i0][j0] + 300.) * ( ((P[k][i0][j0]+PB[k][i0][j0])/100000.)**(2./7.) ) ) )
				ro_kp1 = e_kp1 / ( Rv * ( (T[k+1][i0][j0] + 300.) * ( ((P[k+1][i0][j0]+PB[k+1][i0][j0])/100000.)**(2./7.) ) ) )

				TT = (T[k][i0][j0] + 300.) * (( (P[k][i0][j0]+PB[k][i0][j0])/100000. )**(2./7.))
				PP = (P[k][i0][j0]+PB[k][i0][j0])/100.
				# Model level height is computed using geopotenial H=(PH + PHB)/9.81
				h_k = (PH[k][i0][j0]+PHB[k][i0][j0])/9.81
				h_kp1 = (PH[k+1][i0][j0]+PHB[k+1][i0][j0])/9.81
				delta_height = abs(h_kp1 - h_k)

				# Integrated Water Vapour [kg/m^2]:
				IWV = IWV + ( ((ro_k+ro_kp1) / 2.)  * delta_height )

			#3D data insert:
			cur.execute ( "insert into NWP_IN_3D (Datetime, \
				Temperature, \
				Pressure, \
				SensorID, \
				Latitude, \
				Longitude, \
				Height, \
				WV_Mixing_ratio, \
				Level)\
				values (%s, %s, %s, %s, %s, %s, %s, %s, %s) on duplicate key update\
				Temperature = %s,\
				Pressure = %s,\
				Latitude = %s,\
				Longitude = %s,\
				Height = %s,\
				WV_Mixing_ratio = %s,\
				Level = %s", [date,
				tk,
				Pair,
				sensorId,
				y0,
				x0,
				hgth,
				QV,
				k,
				tk,
				Pair,
				y0,
				x0,
				hgth,
				QV,
				k]) # insert or update
			# Insert IWV into NWP_OUT table:
			cur.execute ( "insert into NWP_OUT (Datetime, \
				StationID, \
				SourceModID, \
				IWV )\
				values (%s, %s, %s, %s) on duplicate key update\
				Datetime = %s,\
				IWV = %s", [
                                    date,
				    stationId,
                                    sourceId,
				    IWV,
                                    date,
                                    IWV
                                ])
		db.commit()
		# commits all data to the specified -d <env>

	
	except Exception as e:
		sys.stderr.write('Error occured in process_station: {error}'.format(error = repr(e)))
	finally:
		return result




# Define a procedure process_station_tro that accumulates data 
# for each station in a dictionary so that it can later be inserted 
# into troposinex txt format. It is similar to the previous 
# procedure process_station that inserts data into the SUADA database.
# If you change one of these two procedures, 
# you should also change the other accordingly.
def process_station_tro(station, ncfile, date):
	result = True
	try:
		stationName = station['name']
		stationId = station['id']
		sensorId = station['senid']
		x0 = station['long']
		y0 = station['latt']
		z0 = station['alt']
		i0 = station['i0']
		j0 = station['j0']
		print 'Station: ', station['name'], ' ID: ', station['id'], ' sensorId: ', sensorId

		# 1D FIELDS:
		# T2, [K]: temperature on 2m height:
		T2 = ncfile.variables['T2'][0]
		# Q2, [kg/kg] - specific humidity (will be inserted in tropo txt format):
		Q2 = ncfile.variables['Q2'][0]
		# Pressure, [Pa]:
		Pressure = ncfile.variables['PSFC'][0]
		# PBLH, [m] - planatary boundary layer height:
		PBLH = ncfile.variables['PBLH'][0]
		# HGT, [m] - 1D height above sea level
		HGT = ncfile.variables['HGT'][0]
		# The following 4 fields are in [mm]:
		RAINNC = ncfile.variables['RAINNC'][0]
		SNOWNC = ncfile.variables['SNOWNC'][0]
		GRAUPELNC = ncfile.variables['GRAUPELNC'][0]
		HAILNC = ncfile.variables['HAILNC'][0]
		# Precipitation, [mm]:
		Precipitation = RAINNC + SNOWNC + GRAUPELNC + HAILNC
		
		# 3D FIELDS:
		# T, [K] - temperature:
		T = ncfile.variables['T'][0]
		# P, [Pa] - perturbation pressure:
		P = ncfile.variables['P'][0]
		# PB, [Pa] - base state pressure
		PB = ncfile.variables['PB'][0]
		# PHB, [m] - base state geopotential height:
		PHB = ncfile.variables['PHB'][0]
		# PH, [m] - perturbation geopotential height:
		PH = ncfile.variables['PH'][0]
		# QVAPOR, [kg/kg] - water vapour mixing ratio:
		QVAPOR = ncfile.variables['QVAPOR'][0]

		# Import 1D fields
		# press, [hPa]:
		press = Pressure[i0][j0]/100.
		# height, [m]:
		heigth = HGT[i0][j0]
		# Q2_humi, [g/kg]:
		Q2_humi = Q2[i0][j0]*1000.
		# Calculation of zhd, [m] - zenith hydrostatic delay
		zhd = (0.0022768*(float(press)))/(1.-0.00266*np.cos(2*(float(z0))*(3.1416/180.))-(0.00028*(float(heigth))/1000.))
		
		# pblh, [m] - planatary boundary layer height:
		pblh = PBLH[i0][j0]
		# temp, [C]:
		temp = T2[i0][j0]-t_kelvin
		# rain, [mm]:
		rain = Precipitation[i0][j0]
	
		print('Inserting into TROPOSINEX txt format. Name: {0} [{1}, {2}, {3}] -> [Temperarture [C]: {4}, Pressure [hPa]: {5}, Rain [mm]: {6}, PBL HEIGHT [m]: {7}, Zenit Heigth Delay [x]: {8}, Q2 [kg/kg]: {9}] '
			.format(station['name'],
				x0,
				y0,
				z0,
				temp,
				press,
				rain,
				pblh,
				zhd,
				Q2_humi))

		# 3D data insertion:
		bottom_top = len(T)
		# First, calculation of tk:
		# Rd, Cp, Rd_Cp are used for 3D calculation of
		# tk (absolute temperature [K], and then
		# it's converted to [C]):
		Rd  = 287.0
		Cp  = 7.0 * Rd / 2.0
		Rd_Cp  = Rd / Cp # dimensionless
		Rv = 461.51
		# The following Tm and k1 are used for calculation of ZWD, ZTD later:
		# Tm, [K] - weighted temperature mean:
		Tm = 70.2 + 0.72 * T2[i0][j0]
		k1 = (10**6) / ( Rv*(((3.766 * 10**5)/Tm) + 22.) )

		IWV = 0.
                # Calculate date variables
                date_YYYY = date.timetuple().tm_year
                date_DOY = date.timetuple().tm_yday
                date_SSSSS = date.timetuple().tm_hour * 60 * 60
		date_HH = date.timetuple().tm_hour
		date_MM = date.timetuple().tm_min
		# Convert to strings:
		YYYY_st = str(date_YYYY)
		DOY_st = '{:03d}'.format(date_DOY)
		SSSSS_st = '{:05d}'.format(date_SSSSS) #str(date_SSSSS)
		HH_st = '{:02d}'.format(date_HH) #str(date_HH)
		MM_st = '{:02d}'.format(date_MM) #str(date_MM)

		for k in range(0, bottom_top):
			if k <= 41:
				# Compute specific humidity q1 and q2 from mixing ratio QVAPOR*1000. in [g/kg]:
				q1 =  (QVAPOR[k][i0][j0] * 1000.) / ( (QVAPOR[k][i0][j0] * 1000.) + 1. )
				q2 =  (QVAPOR[k+1][i0][j0] * 1000.) / ( (QVAPOR[k+1][i0][j0] * 1000.) + 1. )

				# Compute water vapour partial pressure with model pressure = (P+PB)/100. in [hPa]:
				# PP = (P[k][i0][j0]+PB[k][i0][j0])
				e_k   = ( ((P[k][i0][j0]+PB[k][i0][j0]) / 100.)   * q1 ) / ( 0.622 + ( 0.378 * q1 ))
				e_kp1 = ( ((P[k+1][i0][j0]+PB[k+1][i0][j0]) / 100.) * q2 ) / ( 0.622 + ( 0.378 * q2 ))

				# Compute water vapour density with T [K]
				# T is perturbation potential temerature TT=T+300. Total Potential temperature [K]
				# Model level temrature is computed TT = T * ( ((P+PB)/100000.) ^ (2/7)) [K]
				# TT = (T[k][i0][j0] + 300.) * (( (P[k][i0][j0]+PB[k][i0][j0])/100000. )**(2./7.))
				# NB to compute the temerature from potential temprature pressure is in [Pa]

				ro_k   = e_k   / ( Rv * ( (T[k][i0][j0] + 300.) * ( ((P[k][i0][j0]+PB[k][i0][j0])/100000.)**(2./7.) ) ) )
				ro_kp1 = e_kp1 / ( Rv * ( (T[k+1][i0][j0] + 300.) * ( ((P[k+1][i0][j0]+PB[k+1][i0][j0])/100000.)**(2./7.) ) ) )

				TT = (T[k][i0][j0] + 300.) * (( (P[k][i0][j0]+PB[k][i0][j0])/100000. )**(2./7.))
				PP = (P[k][i0][j0]+PB[k][i0][j0])/100.
				# Model level height is computed using geopotenial H=(PH + PHB)/9.81
				h_k = (PH[k][i0][j0]+PHB[k][i0][j0])/9.81
				h_kp1 = (PH[k+1][i0][j0]+PHB[k+1][i0][j0])/9.81
				delta_height = abs(h_kp1 - h_k)

				# Integrated Water Vapour [kg/m^2]:
				IWV = IWV + ( ((ro_k+ro_kp1) / 2.)  * delta_height )

		# Compute Zenith Wet Delay (ZWD, [m]) and Zenith Total Delay (ZTD, [m]):
		ZWD = IWV/(k1*100.) # Divided by 100 to convert from [cm] to [m].
		ZTD = zhd + ZWD

		# In the TROPOSINEX format, zhd, ZTD, ZWD are in [mm]. Therefore, *1000. :
		zhd_mm = zhd*1000.
		ZWD_mm = ZWD*1000.
		ZTD_mm = ZTD*1000.

		# Create result as a dictonary:
		result = {
			'station_name' : station['name'],
			'long'         : station['long'],
			'latt'         : station['latt'],
			'alt'          : station['alt'],
			'IWV'          : IWV,
			'press'        : press,
			'Q2_humi'      : Q2_humi,
			'temp'         : temp,
			'Tm'           : Tm,
			'zhd_mm'       : zhd_mm,
			'ZTD_mm'       : ZTD_mm,
			'ZWD_mm'       : ZWD_mm,
			'q1'           : q1,
			'q2'           : q2,
			'YYYY_st'      : YYYY_st,
			'DOY_st'       : DOY_st,
			'SSSSS_st'     : SSSSS_st,
			'HH_st'        : HH_st,
			'MM_st'        : MM_st
			}

	except Exception as e:
		sys.stderr.write('Error occured in process_station_tro: {error}'.format(error = repr(e)))
	finally:
		return result


# Define a procedure that exports the accumulated data
# from the process_station_tro procedure into
# TROPOSINEX txt format:
# ( SINEX_TRO - Solution INdependent EXchange format for
# TROpospheric and meteorological parameters. )
def tropo_out(station_data):
	result = True
	try:
		# Insert values of parameters in txt format:
		# Generating filename as required TROPOSINEX format:
		for station in station_data:
			YYYY_st = station['YYYY_st']
			DOY_st = station['DOY_st']
			HH_st = station['HH_st']
			MM_st = station['MM_st']
			filename = 'SUG1_UNK_UNK_'+YYYY_st+DOY_st+HH_st+MM_st+'_00U_00U.TRO'
		# Inserting data into the TROPOSINEX format:
		with open(filename, 'w') as troposinex:
			troposinex.write('%=TRO \
\n\
\n*---------------------------------------------------------------------------- \
\n+FILE/REFERENCE \
\n*INFO_TYPE_____ \
\nINFO______________________________ \
\nDESCRIPTION		SUGAC \
\nOUTPUT			SUGAC \
\nCONTACT			GUEROVA \
\nSOFTWARE		WRFv3.7.1 \
\nINPUT			NWM \
\nVERSION NUMBER		001 \
\n-FILE/REFERENCE \
\n\
\n*---------------------------------------------------------------------------- \
\n+TROP/DESCRIPTION \
\n*_____KEYWORD_______\
\n__VALUE(S)________________\
\nREFRACTIVITY COEFFICIENTS 	77.60 70.40 373900.0\
\nTROPO SAMPLING INTERVAL 	3600\
\nTIME SYSTEM 			UTC\
\nTROPO PARAMETER NAMES		IWV PRESS HUMSPC TEMDRY WMTEMP TRODRY TROTOT TROWET\
\nTROPO PARAMETER UNITS		1 1 1 1 1 1e+03 1e+03 1e+03\
\nTROPO PARAMETER WIDTH		6 6 7 6 6 6 6 6 6\
\n-TROP/DESCRIPTION \
\n\
\n*---------------------------------------------------------------------------- \
\n+SITE/ID \
\n*STATION__ _LONGITUDE _LATITUDE_ _HGT_MSL_ \
')
			for station in station_data:
				troposinex.write('\n{name:12s} {longit:>5.6f} {latt:>5.6f} {alt:>5.6f}'
					.format(
					name     = station['station_name'][:12],
					longit   = station['long'],
					latt     = station['latt'],
					alt      = station['alt']
				))
			troposinex.write(' \n \
\n-SITE/ID \
\n\
\n*---------------------------------------------------------------------------- \
\n+SITE/COORDINATES \
\n*STATION \
\n\
\n-SITE/COORDINATES \
\n\
\n*---------------------------------------------------------------------------- \
\n+TROP/SOLUTION \
\n*STATION__ ____EPOCH___ IWV PRESS HUMSPC TEMPDRY WMTEMP TRODRY TROTOT TROWET \
')
# FIELD NAMES:
# Station = station name
# Epoch   = timestamp YY:DDD:SSSSS
# IWV     = Integrated water vapour, [kg/m^2]
# PRESS   = Pressure, [Pa]
# HUMSPC  = Specific humidity q, [g/kg]
# TEMPDRY = Dry temperature temp, [K]
# WMTEMP  = Weighted mean temperature Tm, [K]
# TRODRY  = zhd_mm, [mm]
# TROTOT  = ZTD_mm, [mm]
# TROWET  = ZWD_mm, [mm]
			for station in station_data:
				troposinex.write('\n {name:9s} {epoch:12s} {IWV:>5.2f} {press:>5.2f} {humi_spc:>5.3f} {temp:>5.1f} {Tm:>5.1f} {TRODRY:>5.1f} {TROTOT:>5.1f} {TROWET:>5.1f}'
					.format(
					name     = station['station_name'][:9],
					epoch    = station['YYYY_st']+':'+station['DOY_st']+':'+station['SSSSS_st'],
					IWV      = station['IWV'],
					press    = station['press'],
					humi_spc = station['Q2_humi'],
					temp     = station['temp']+t_kelvin,
					Tm       = station['Tm'],
					TRODRY   = station['zhd_mm'],
					TROTOT   = station['ZTD_mm'],
					TROWET   = station['ZWD_mm']
				))
			troposinex.write(' \n \
\n-TROP/SOLUTION \
\n\
\n%=ENDTRO \
\n\
')
			troposinex.close()

	except Exception as e:
		sys.stderr.write('Error occured in tropo_out: {error}'.format(error = repr(e)))
		result = False
	finally:
		return result



# Define the main procedure that checks whether the command
# that the user typed in the terminal is correct; then it has to
# create a db connection; to fetch source_id by calling
# the procedure get_source_id; then call the procedure
# getstations that selects the stations' information
# from the SUADA information tables. (The SUADA information tables
# are: INSTRUMENT, STATION, COORDINATE, SENSOR and SOURCE.)
# Then to iterate through all stations that satisfy the conditions
# that the user specified and to obtain model data.
# Lastly, depending on the user's choice on -o <output>
# (either -o db or -o tro), the process_station or
# process_station_tro procedure is called.
# The process_station procedure inserts the model data
# into a SUADA database. The process_station_tro generates
# a dictionary that will be exported to Troposinex txt format.

def main(argv):
	# Optional for the user to specify are the following
	# parameters:
	# -b <basedir>
	# -p <prefix>
	# -c <country> - the country in which all stations
	# will be iterated through.
	# (If not specified - the script iterates through
	# all countries.)
	# Mandatory for the user to specify are the following:
	# -s <source_name> - each user has a specific source_name
	# that they should know (if not, see Instructions, point 7).
	# -d <env> - the environment in which the data from the
	# WRF model is going to be stored.
	# -o <output> - either insert data into database or
	# export it to txt fomrat.
	basedir='./'
	prefix='wrfout_d02'
	source_name = ''
	country = 'All' # By default: 'All'.
	# Possible options are 'BG', 'GR', ...
	env = '' # possible options are 'dev' and 'prod'.
	output = 'db' # By default: 'db'.
	# Possible options: 'db' (write to SUADA db),
	# 'tro' (write to troposinex txt format).
	instrument_name = 'GNSS'

	try:
		opts, args = getopt.getopt(argv,"h:b:p:s:c:d:o:",["basedir=","prefix=","source_name=","country=","env=","output="])
	except getopt.GetoptError:
		print 'ncdf2db.py -b <basedir> ['+basedir+'] -p <prefix> ['+prefix+'] -s <source_name> ['+str(source_name)+'] -c <country> ['+str(country)+'] -d <env> ['+str(env)+'] -o <output> ['+str(output)+']'
		sys.exit(2)
	for opt, arg in opts:
		if opt == '-h':
			print 'ncdf2db.py -b <basedir> ['+basedir+'] -p <prefix> ['+prefix+'] -s <source_name> ['+str(source_name)+'] -c <country> ['+str(country)+'] -d <env> ['+str(env)+'] -o <output> ['+str(output)+']'
			sys.exit()
		elif opt in ("-b", "--basedir"):
			basedir = arg
		elif opt in ("-p", "--prefix"):
			prefix = arg
		elif opt in ("-s", "--source_name"):
			source_name = str(arg)
		elif opt in ("-c", "--country"):
			if country:
				country = str(arg)
			else:
				country = 'All'
		elif opt in ("-d", "--env"):
			env = str(arg)
		elif opt in ("-o", "--output"):
			output = str(arg)

	# Check whether the user has specified source name.
	# If not -> Error.
	if source_name == '':
		print 'Error: You must specify the source name! (-s <source_name>)'
		sys.exit()

	# Check whether the user has specified the database.
	# If not -> Error.
	if env == '':
		print 'Error: You must specify the database! (-d <env>)'
		sys.exit()

	if not output in {'db', 'tro'}:
		print ('Error: Not a possible output {}'.format(output))
		sys.exit()

	# Retrieve the list of all data files
	# starting with [prefix] inside [basedir] folder
	flist = listfiles(basedir, prefix)

	# Create the DB connection:
	db = None
	cur = None
	try:
		if env == 'dev':
			print('DB -> {}'.format(cfg.dev['db']))
			db = MySQLdb.connect(host=cfg.dev['host'], \
				user=cfg.dev['user'], \
				passwd=cfg.dev['passwd'], \
				db=cfg.dev['db'])
		elif env == 'prod':
			print('DB -> {}'.format(cfg.prod['db']))
			db = MySQLdb.connect(host=cfg.prod['host'], \
				user=cfg.prod['user'], \
				passwd=cfg.prod['passwd'], \
				db=cfg.prod['db'])
		elif env != {'dev','prod'}:
			print 'Error: No such database! (Possible options for -d <env> are "dev" and "prod".)'
			sys.exit()
		cur = db.cursor()
	except Exception as e:
		print('Failed to establish connection: {0}'.format(e))
		cur.close()
		sys.exit(1)

	# Fetching source_id...
	print('Trying to fetch the source_id ...')
	source_id = get_source_id(cur, source_name)
	if source_id < 0:
		print 'Error: Can not find source_id for source_name: {}'.format(source_name)
		sys.exit(1)

	print('Source id: {} found for source name: {}'.format(source_id, source_name))

	# Call the procedure that selects the stations' information
	# from the SUADA information tables:
	print('Get stations')
	stations = getstations(cur, source_name, country, instrument_name)

	# Now iterating over list of all data files:
	print('Iterate files')

	for file in flist:
		field2D = []
		print 'Processing: ', file
		ncfile = netcdf(file)
		strDateTime = ncfile.variables['Times'][0].tostring().replace('_', ' ')
		local_tz = get_localzone()
		date = parser.parse(strDateTime)
		strDateTimeLocal = local_tz.localize(date)
		# Print the timestamp
		print('Dataset timestamp: {}'.format(strDateTimeLocal))
		xlong = ncfile.variables['XLONG'][0]
		xlat = ncfile.variables['XLAT'][0]
		alt = ncfile.variables['HGT'][0]
		truelat1 = ncfile.TRUELAT1
		truelat2 = ncfile.TRUELAT2
		ref_lat  = ncfile.CEN_LAT
		ref_lon  = ncfile.CEN_LON
		stand_lon= ncfile.STAND_LON
		dx = ncfile.DX
		dy = ncfile.DY
		west_east = ncfile.dimensions['west_east'].size
		south_north = ncfile.dimensions['south_north'].size


		# Empty list to contain data:
		station_data = []
		for station in stations:
			stationName = station['name']
			stationId = station['id']
			sensorId = station['senid']
			print 'Station: ', station['name'], ' ID: ', station['id'], ' sensorId: ', sensorId, 'Country Code: ', station['country']
			x0 = station['long']
			y0 = station['latt']
			z0 = station['alt']
			indx = wrf.ll_to_ij(1, truelat1, truelat2, stand_lon, dx, dy, ref_lat, ref_lon, y0, x0)
			j0 = west_east / 2 + indx[0] - 1
			i0 = south_north / 2 + indx[1] - 1
			station['i0'] = i0
			station['j0'] = j0
                        station['source_id'] = source_id


			if (i0 >= 0 and i0 < south_north) and ( j0 >= 0 and j0 < west_east) and ( (country == 'All') or (country == station['country'])):
				if output == 'db':
					process_station(db, cur, station, ncfile, date)
				elif output == 'tro':
					# save result in
					# tropo_station_data
					tropo_station_data = process_station_tro(station, ncfile, date)
					# if tropo_station_data is
					# not None,
					# append to data list
					if tropo_station_data:
						station_data.append(tropo_station_data.copy())
		if output == 'tro' and len(station_data)>0:
			tropo_out(station_data)

	if not(len(flist)):
		print 'No candidates for import files found ...'
		sys.exit(1)

if __name__ == "__main__":
	main(sys.argv[1:])
