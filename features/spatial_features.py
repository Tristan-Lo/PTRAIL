"""
    The spatial_features  module contains several functions of the library
    that calculates many features based on the DateTime provided in
    the data. This module mostly extracts and modifies data collected from
    some existing dataframe and appends these information to them. It is to
    be also noted that a lot of these features are inspired from the PyMove
    library and we are crediting the PyMove creators with them.

    @authors Yaksh J Haranwala, Salman Haidri
    @date 2nd June, 2021
    @version 1.0
    @credits PyMove creators
"""
import itertools
import multiprocessing
from typing import Optional, Text

import numpy as np
import pandas as pd

from core.TrajectoryDF import NumPandasTraj
from features.helper_functions import Helpers as helpers
from utilities import constants as const
from utilities.DistanceCalculator import DistanceFormulaLog as calc


class SpatialFeatures:
    @staticmethod
    def get_bounding_box(dataframe: NumPandasTraj):
        """
            Return the bounding box of the Trajectory data. Essentially, the bounding box is of
            the following format:
                (min Latitude, min Longitude, max Latitude, max Longitude).

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe containing the trajectory data.

            Returns
            -------
                tuple
                    The bounding box of the trajectory
        """
        return (
            dataframe[const.LAT].min(),
            dataframe[const.LONG].min(),
            dataframe[const.LAT].max(),
            dataframe[const.LONG].max(),
        )

    @staticmethod
    def get_start_location(dataframe: NumPandasTraj, traj_id=None):
        """
            Get the starting location of an object's trajectory in the data.
            Note that if the data does not have an Object ID column and does not have unique objects,
            then the entire dataset's starting location is returned.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The DaskTrajectoryDF storing the trajectory data.
                traj_id
                    The ID of the object whose start location is to be found.

            Returns
            -------
                tuple
                    The (lat, longitude) tuple containing the start location.
        """
        # If traj_id is None, filter out a dataframe with the earliest time and then return the first 
        # latitude and longitude at that time.
        # Else first filter out a dataframe containing the given traj_id and then perform the same steps as
        # mentioned above
        dataframe = dataframe.copy().reset_index()
        if traj_id is None:
            start_loc = (dataframe.loc[dataframe[const.DateTime] == dataframe[const.DateTime].min(),
                                       [const.LAT, const.LONG]]).reset_index()
            return start_loc[const.LAT][0], start_loc[const.LONG][0]
        else:
            filt = (dataframe.loc[dataframe[const.TRAJECTORY_ID] == traj_id, [const.DateTime, const.LAT, const.LONG]])
            start_loc = (filt.loc[filt[const.DateTime] == filt[const.DateTime].min(),
                                  [const.LAT, const.LONG]]).reset_index()
            if len(start_loc) == 0:
                return f"Trajectory ID: {traj_id} does not exist in the dataset. Please try again!"
            else:
                return start_loc[const.LAT][0], start_loc[const.LONG][0]

    @staticmethod
    def get_end_location(dataframe: NumPandasTraj, traj_id: Optional[Text] = None):
        """
            Get the ending location of an object's trajectory in the data.
            Note: If the user does not provide a trajectory id, then the last
            Parameters
            ----------
                dataframe: DaskTrajectoryDF
                    The DaskTrajectoryDF storing the trajectory data.
                traj_id
                    The ID of the trajectory whose end location is to be found.
            Returns
            -------
                tuple
                    The (lat, longitude) tuple containing the end location.
        """
        # If traj_id is None, filter out a dataframe with the latest time and then return the last
        # latitude and longitude at that time.
        # Else first filter out a dataframe containing the given traj_id and then perform the same steps as
        # mentioned above
        dataframe = dataframe.copy().reset_index()
        if traj_id is None:
            start_loc = (dataframe.loc[dataframe[const.DateTime] == dataframe[const.DateTime].max(),
                                       [const.LAT, const.LONG]]).reset_index()
            return start_loc[const.LAT][0], start_loc[const.LONG][0]
        else:
            filt = (dataframe.loc[dataframe[const.TRAJECTORY_ID] == traj_id, [const.DateTime, const.LAT, const.LONG]])
            start_loc = (filt.loc[filt[const.DateTime] == filt[const.DateTime].max(),
                                  [const.LAT, const.LONG]]).reset_index()
            if len(start_loc) == 0:
                return f"Trajectory ID: {traj_id} does not exist in the dataset. Please try again!"
            else:
                return start_loc[const.LAT][0], start_loc[const.LONG][0]

    @staticmethod
    def create_distance_between_consecutive_column(dataframe: NumPandasTraj):
        """
            Create a column called Dist_prev_to_curr containing distance between 2 consecutive points.
            The distance calculated is the Great-Circle distance.
            NOTE: When the trajectory ID changes in the data, then the distance calculation again starts
                  from the first point of the new trajectory ID and the first point of the new trajectory
                  ID will be set to 0.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The data where speed is to be calculated.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.
        """
        chunks = []  # list for storing the smaller parts of the original dataframe.

        # Now, lets split the given dataframe into smaller pieces of 75000 rows each
        # so that we can run parallel tasks on each smaller piece.
        for i in range(0, len(dataframe), 75001):
            chunks.append(dataframe.reset_index().loc[i: i + 75000])

        # Now, lets create a pool of processes which contains processes equal to the number
        # of smaller chunks and then run them in parallel so that we can calculate
        # the distance for each smaller chunk and then merge all of them together.
        multi_pool = multiprocessing.Pool(len(chunks))
        result = multi_pool.map(helpers._consecutive_distance_helper, chunks)

        # Now lets, merge the smaller pieces and then return the dataframe
        result = pd.concat(result)
        return NumPandasTraj(result, const.LAT, const.LONG, const.DateTime, const.TRAJECTORY_ID)

    @staticmethod
    def create_distance_from_start_column(dataframe: NumPandasTraj):
        """
            Create a column containing distance between the start location and the rest of the
            points using Haversine formula. The distance calculated is the Great-Circle distance.
            NOTE: When the trajectory ID changes in the data, then the distance calculation again
                  starts from the first point of the new trajectory ID and the first point of the
                  new trajectory ID will be set to 0.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The data where speed is to be calculated.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.
        """
        partitions = []  # List for storing the smaller partitions.

        # Now, lets partition the dataframe into smaller sets of 75000 rows each
        # so that we can perform parallel calculations on it.
        for i in range(0, len(dataframe), 75001):
            partitions.append(dataframe.reset_index().loc[i:i + 75000])

        # Now, lets create a multiprocessing pool of processes and then create as many
        # number of processes as there are number of partitions and run each process in parallel.
        pool = multiprocessing.Pool(len(partitions))
        answer = pool.map(helpers._start_distance_helper, partitions)

        answer = pd.concat(answer)
        return NumPandasTraj(answer, const.LAT, const.LONG, const.DateTime, const.TRAJECTORY_ID)

    @staticmethod
    def get_distance_by_date_and_traj_id(dataframe: NumPandasTraj, date, traj_id=None):
        """
            Given a date and trajectory ID, this function calculates the total distance
            covered in the trajectory on that particular date and returns it.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe in which teh actual data is stored.
                date: Text
                    The Date on which the distance covered is to be calculated.
                traj_id: Text
                    The trajectory ID for which the distance covered is to be calculated.

            Returns
            -------
                float
                    The total distance covered on that date by that trajectory ID.
        """
        # First, reset the index of the dataframe.
        # Then, filter the dataframe based on Date and Trajectory ID if given by user.
        data = dataframe.reset_index()
        filt = data.loc[data[const.DateTime].dt.date == pd.to_datetime(date)]
        small = filt.loc[filt[const.TRAJECTORY_ID] == traj_id] if traj_id is not None else filt

        # First, lets fetch the latitude and longitude columns from the dataset and store it
        # in a numpy array.
        traj_ids = np.array(small.reset_index()[const.TRAJECTORY_ID])
        latitudes = np.array(small[const.LAT])
        longitudes = np.array(small[const.LONG])
        distances = np.zeros(len(traj_ids))

        # Now, lets calculate the Great-Circle (Haversine) distance between the 2 points and store
        # each of the values in the distance numpy array.
        for i in range(len(latitudes) - 1):
            distances[i + 1] = calc.haversine_distance(latitudes[i], longitudes[i], latitudes[i + 1], longitudes[i + 1])

        return np.sum(distances)  # Sum all the distances and return the total path length.

    @staticmethod
    def create_point_within_range_column(dataframe: NumPandasTraj, coordinates: tuple,
                                         dist_range: float):
        """
            Checks how many points are within the range of the given coordinate. By first making a column
            containing the distance between the given coordinate and rest of the points in dataframe by calling
            create_distance_from_point(). And then comparing each point using the condition if it's within the
            range and appending the values in a column and attaching it to the dataframe.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe on which the point within range calculation is to be done.
                coordinates: tuple
                    The coordinates from which the distance is to be calculated.
                dist_range: float
                    The range within which the resultant distance from the coordinates should lie.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.

        """
        dataframe_list = []  # List for storing the smaller partitions.

        # Now, lets partition the dataframe into smaller sets of 75000 rows each
        # so that we can perform parallel calculations on it.
        for i in range(0, len(dataframe), 75001):
            dataframe_list.append(dataframe.reset_index().loc[i: i + 75000])

        # Now, lets create a multiprocessing pool of processes and then create as many
        # number of processes as there are number of partitions and run each process in parallel.
        pool = multiprocessing.Pool(len(dataframe_list))
        args = zip(dataframe_list, itertools.repeat(coordinates), itertools.repeat(dist_range))
        result = pool.starmap(helpers._point_within_range_helper, args)

        # Now lets join all the smaller partitions and return the resultant dataframe
        result = pd.concat(result)
        return NumPandasTraj(result, const.LAT, const.LONG, const.DateTime, const.TRAJECTORY_ID)

    @staticmethod
    def create_distance_from_given_point_column(dataframe: NumPandasTraj, coordinates: tuple):
        """
            Given a point, this function calculates the distance between that point and all the
            points present in the dataframe and adds that column into the dataframe.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe on which calculation is to be done.
                coordinates: tuple
                    The coordinates from which the distance is to be calculated.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.
        """
        part_list = []  # List for storing the smaller partitions.

        # Now, lets partition the dataframe into smaller sets of 75000 rows each
        # so that we can perform parallel calculations on it.
        for i in range(0, len(dataframe), 75001):
            part_list.append(dataframe.reset_index().loc[i:i + 75000])

        # Now, lets create a multiprocessing pool of processes and then create as many
        # number of processes as there are number of partitions and run each process in parallel.
        pool = multiprocessing.Pool(len(part_list))
        answer = pool.starmap(helpers._given_point_distance_helper, zip(part_list, itertools.repeat(coordinates)))

        # Now lets join all the smaller partitions and then add the Distance to the
        # specific point column.
        answer = pd.concat(answer)

        # return the answer dataframe converted to NumPandasTraj.
        return NumPandasTraj(answer, const.LAT, const.LONG, const.DateTime, const.TRAJECTORY_ID)

    @staticmethod
    def create_speed_from_prev_column(dataframe: NumPandasTraj):
        """
            Create a column containing speed of the object from the start to the current
            point.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe on which the calculation of speed is to be done.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.
        """
        # Here, we are using try and catch blocks to check whether the DataFrame has the
        # Distance_prev_to_curr column.
        try:
            # If the Distance_prev_to_curr column is already present in the dataframe,
            # then extract it, calculate the time differences between the consecutive
            # rows in the dataframe and then calculate distances/time_deltas in order to
            # calculate the speed.
            distances = dataframe.reset_index()['Distance_prev_to_curr']
            time_deltas = dataframe.reset_index()[const.DateTime].diff().dt.seconds

            # Assign the new column and return the NumPandasTrajDF.
            dataframe['Speed_prev_to_curr'] = (distances/time_deltas).to_numpy()
            return dataframe

        except KeyError:
            # If the Distance_prev_to_curr column is not present in the Dataframe and a KeyError
            # is thrown, then catch it and the overridden behaviour is as follows:
            #   1. Calculate the distance by calling the create_distance_between_consecutive_column() function.
            #   2. Calculate the time deltas.
            #   3. Divide the 2 values to calculate the speed.
            dataframe = SpatialFeatures.create_distance_between_consecutive_column(dataframe)
            distances = dataframe.reset_index()['Distance_prev_to_curr']
            time_deltas = dataframe.reset_index()[const.DateTime].diff().dt.seconds

            # Assign the column and return the NumPandasTrajDF.
            dataframe['Speed_prev_to_curr'] = (distances/time_deltas).to_numpy()
            return dataframe

    @staticmethod
    def create_acceleration_from_prev_column(dataframe: NumPandasTraj):
        """
            Create a column containing acceleration of the object from the start to the current
            point.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe on which the calculation of acceleration is to be done.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.
        """
        # Try catch is used to check if speed column is present or not
        try:
            # When Speed column is present extract the data from there and then take calculate the time delta
            # And use that to calculate acceleration by dividing speed by time delta and then add the column to
            # the dataframe
            speed_deltas = dataframe.reset_index()['Speed_prev_to_curr'].diff()
            time_deltas = dataframe.reset_index()[const.DateTime].diff().dt.seconds

            dataframe['Acceleration_prev_to_curr'] = (speed_deltas/time_deltas).to_numpy()
            return dataframe

        except KeyError:
            # When Speed column is not present then first call create_speed_from_prev_column() function to make
            # the speed column and then follow the steps mentioned above
            dataframe = SpatialFeatures.create_speed_from_prev_column(dataframe)
            speed_deltas = dataframe.reset_index()['Speed_prev_to_curr'].diff()
            time_deltas = dataframe.reset_index()[const.DateTime].diff().dt.seconds

            dataframe['Acceleration_prev_to_curr'] = (speed_deltas / time_deltas).to_numpy()
            return dataframe

    @staticmethod
    def create_jerk_from_prev_column(dataframe: NumPandasTraj):
        """
            Create a column containing jerk of the object from the start to the current
            point.

            Parameters
            ----------
                dataframe: NumPandasTraj
                    The dataframe on which the calculation of jerk is to be done.

            Returns
            -------
                core.TrajectoryDF.NumPandasTraj
                    The dataframe containing the resultant column.
        """
        # Try catch is used to check if acceleration column is present or not
        try:
            # When acceleration column is present extract the data from there and then take calculate the time delta
            # And use that to calculate acceleration by dividing speed_delta by time delta and then add the column to
            # the dataframe
            acceleration_deltas = dataframe.reset_index()['Acceleration_prev_to_curr'].diff()
            time_deltas = dataframe.reset_index()[const.DateTime].diff().dt.seconds

            dataframe['jerk_prev_to_curr'] = (acceleration_deltas/time_deltas).to_numpy()
            return dataframe

        except KeyError:
            # When Speed column is not present then first call create_speed_from_prev_column() function to make
            # the speed column and then follow the steps mentioned above
            dataframe = SpatialFeatures.create_acceleration_from_prev_column(dataframe)
            acceleration_deltas = dataframe.reset_index()['Acceleration_prev_to_curr'].diff()
            time_deltas = dataframe.reset_index()[const.DateTime].diff().dt.seconds

            dataframe['jerk_prev_to_curr'] = (acceleration_deltas / time_deltas).to_numpy()
            return dataframe

    @staticmethod
    def create_bearing_column(dataframe: NumPandasTraj):
        pass

    @staticmethod
    def create_bearing_rate_column(dataframe: NumPandasTraj):
        pass

    @staticmethod
    def create_rate_of_bearing_rate_column(dataframe: NumPandasTraj):
        pass
