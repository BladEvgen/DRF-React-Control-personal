import React, { useState, useEffect, useRef } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import Notification from "../components/Notification";
import AnimatedMarker from "../components/AnimatedMarker";
import { BaseAction } from "../schemas/BaseAction";
import { LocationData } from "../schemas/IData";

const fallbackLocations: LocationData[] = [
  {
    name: "Главный Корпус (Абылайхана)",
    lat: 43.2644734,
    lng: 76.9393907,
    employees: 1000,
  },
  {
    name: "Второй Корпус (Торекулова)",
    lat: 43.2655509,
    lng: 76.9299558,
    employees: 500,
  },
  {
    name: "Третий Корпус (Карасай батыра)",
    lat: 43.251326,
    lng: 76.9349449,
    employees: 200,
  },
  {
    name: "Тест",
    lat: 43.271326,
    lng: 76.9349449,
    employees: 200,
  },
  {
    name: "Тест2",
    lat: 43.251326,
    lng: 76.9649449,
    employees: 200,
  },
  {
    name: "Тест3",
    lat: 43.253396,
    lng: 76.9649449,
    employees: 200,
  },
];

const generateColorSet = (numColors: number, theme: string): string[] => {
  const colors = [];
  for (let i = 0; i < numColors; i++) {
    let hue = (i * 137) % 360;
    if (theme === "light" && ((hue >= 0 && hue <= 30) || hue >= 330)) {
      hue = (hue + 60) % 360;
    }

    const saturation =
      theme === "dark"
        ? `${30 + Math.random() * 30}%`
        : `${70 + Math.random() * 30}%`;
    const lightness =
      theme === "dark"
        ? `${60 + Math.random() * 10}%`
        : `${40 + Math.random() * 20}%`;

    colors.push(`hsl(${hue}, ${saturation}, ${lightness})`);
  }
  return colors;
};

const areColorsSimilar = (
  color1: string,
  color2: string,
  tolerance: number
): boolean => {
  const hue1 = parseInt(color1.match(/\d+/)![0]);
  const hue2 = parseInt(color2.match(/\d+/)![0]);
  const hueDiff = Math.abs(hue1 - hue2);
  return hueDiff < tolerance;
};

const calculateDistance = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
) => {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
};

const selectBestColor = (
  colors: string[],
  location: LocationData,
  existingLocations: LocationData[],
  assignedColors: { [key: string]: string }
): string => {
  for (let color of colors) {
    let isValid = true;
    for (let loc of existingLocations) {
      const distance = calculateDistance(
        location.lat,
        location.lng,
        loc.lat,
        loc.lng
      );
      const assignedColor = assignedColors[loc.name];

      if (distance < 0.3 && areColorsSimilar(color, assignedColor, 20)) {
        isValid = false;
        break;
      }
    }
    if (isValid) return color;
  }
  return colors[0];
};

const MapPage: React.FC = () => {
  const [locations, setLocations] = useState<LocationData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visiblePopup, setVisiblePopup] = useState<string | null>(null);
  const [theme] = useState<string>(localStorage.getItem("theme") || "light");
  const [tileLayerUrl] = useState(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
  );
  const [isMarkersVisible, setIsMarkersVisible] = useState(false);
  const mapRef = useRef<L.Map | null>(null);
  const colors = useRef<string[]>([]);
  const assignedColors: { [key: string]: string } = {};

  useEffect(() => {
    const fetchLocations = async () => {
      setLoading(true);
      let fetchedLocations: LocationData[] = [];
      try {
        const response = await axiosInstance.get(`${apiUrl}/api/locations`);
        fetchedLocations = response.data;
        setLocations(fetchedLocations);
        new BaseAction(BaseAction.SET_DATA, fetchedLocations);
      } catch (error) {
        fetchedLocations = fallbackLocations;
        setError("Не удалось загрузить данные.");
        setLocations(fallbackLocations);
        new BaseAction<string>(BaseAction.SET_ERROR, "Ошибка загрузки данных");
      } finally {
        setLoading(false);
      }

      colors.current = generateColorSet(fetchedLocations.length, theme);

      setTimeout(() => {
        setIsMarkersVisible(true);
        const firstLocation =
          fetchedLocations.length > 0
            ? fetchedLocations[0].name
            : fallbackLocations[0].name;
        setTimeout(() => {
          setVisiblePopup(firstLocation);
        }, 1500);
      }, 1000);
    };

    fetchLocations();
  }, [theme]);

  const toggleVisibility = (location: LocationData) => {
    setVisiblePopup(visiblePopup === location.name ? null : location.name);
    if (mapRef.current) {
      mapRef.current.setView(
        [location.lat, location.lng],
        mapRef.current.getZoom(),
        {
          animate: true,
        }
      );
    }
  };

  const customIcon = L.icon({
    iconUrl: `${apiUrl}/media/marker.png`,
    iconSize: [35, 40],
    iconAnchor: [17, 35],
    popupAnchor: [0, -40],
  });

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen">
        <div className="loader"></div>
        <p className="mt-4 text-lg text-gray-300 dark:text-gray-400">
          Данные загружаются, пожалуйста, подождите...
        </p>
      </div>
    );
  }

  if (error) {
    return <Notification message={error} type="error" link="/" />;
  }

  return (
    <div className="relative h-screen w-screen p-4 md:p-8 lg:p-12">
      <MapContainer
        center={[43.2644734, 76.9393907]}
        zoom={13.5}
        style={{ width: "100%", height: "100%" }}
        className="rounded-lg shadow-lg border border-gray-300 dark:border-gray-700"
        tap={false}
        ref={mapRef}
      >
        <TileLayer url={tileLayerUrl} />

        {locations.map((location, index) => {
          if (!assignedColors[location.name]) {
            assignedColors[location.name] = selectBestColor(
              colors.current,
              location,
              locations.slice(0, index),
              assignedColors
            );
          }
          const circleColor = assignedColors[location.name];

          return (
            <AnimatedMarker
              key={index}
              position={[location.lat, location.lng]}
              name={location.name}
              employees={location.employees}
              isVisible={isMarkersVisible}
              icon={customIcon}
              onClick={() => toggleVisibility(location)}
              popupVisible={visiblePopup === location.name}
              theme={theme}
              radius={120}
              color={circleColor}
            />
          );
        })}
      </MapContainer>
    </div>
  );
};

export default MapPage;
