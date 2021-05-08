import math
import os


class GeoLocation:
    def __init__(self, mylat, mylang):
        self.mylat = mylat
        self.mylang = mylang

    def degreesToRadians(self, degree):
        return degree * math.pi / 180

    def calculate_dist(self, lat, lang, max_dist):
        earth_radius = 6371

        dlat = self.degreesToRadians(lat - self.mylat)
        dlon = self.degreesToRadians(lang - self.mylang)

        lat1 = self.degreesToRadians(lat)
        lat2 = self.degreesToRadians(self.mylat)

        a = (math.sin(dlat/2) * math.sin(dlat/2) +
             math.sin(dlon/2) * math.sin(dlon/2) *
             math.cos(lat1) * math.cos(lat2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        '''
        print("loc1=(%s, %s) loc2=(%s, %s), dist=%s" % (
            self.mylat, self.mylang, lat, lang, c * earth_radius))
        '''
        if earth_radius * c < max_dist:
            return True
        else:
            return False


if __name__ == "__main__":
    lat = float(os.environ["CURRENT_LAT"])
    longitude = float(os.environ["CURRENT_LONG"])
    gl = GeoLocation(lat, longitude)
    d = gl.calculate_dist(12.897550, 77.593830, 5)
    print(d)
    d = gl.calculate_dist(12.944093577762436, 77.69604881493385, 5)
    print(d)
    d = gl.calculate_dist(12, 77, 5)
    print(d)
