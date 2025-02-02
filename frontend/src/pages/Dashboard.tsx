import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Line } from "react-chartjs-2";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";

import { Chart as ChartJS, registerables, TooltipItem } from "chart.js";
import { AttendanceStats } from "../schemas/IData";
import Notification from "../components/Notification";
import LoaderComponent from "../components/LoaderComponent";
ChartJS.register(...registerables);

const Dashboard: React.FC<{ pin?: string }> = ({ pin }) => {
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [, setTheme] = useState<string>(
    () => localStorage.getItem("theme") || "light"
  );
  const [selectedDate] = useState<string>(
    (() => {
      const date = new Date();
      date.setDate(date.getDate() - 1);
      return date.toISOString().split("T")[0];
    })()
  );

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params: any = { date: selectedDate };

      if (pin) {
        params.pin = pin;
      }

      const response = await axiosInstance.get(
        `${apiUrl}/api/attendance/stats/`,
        {
          params,
        }
      );
      setStats(response.data);
    } catch (err) {
      console.error(err);
      setError("Ошибка при загрузке данных. Пожалуйста, попробуйте позже.");
    } finally {
      setLoading(false);
    }
  }, [selectedDate, pin]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const handleThemeChange = () => {
      setTheme(localStorage.getItem("theme") || "light");
    };
    window.addEventListener("storage", handleThemeChange);

    return () => {
      window.removeEventListener("storage", handleThemeChange);
    };
  }, []);

  useEffect(() => {
    if (!loading && !stats && !error) {
      const timeout = setTimeout(() => {
        setError("Данные не были найдены.");
      }, 5000);
      return () => clearTimeout(timeout);
    }
  }, [loading, stats, error]);

  const formatDate = (dateString: string) => {
    const options: Intl.DateTimeFormatOptions = {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    };
    return new Date(dateString).toLocaleDateString("ru-RU", options);
  };

  const chartData = useMemo(() => {
    if (!stats) return null;

    const filteredData = stats.present_data
      .map((staff) => ({
        ...staff,
        individual_percentage: Math.ceil(staff.individual_percentage),
      }))
      .filter(
        (staff) =>
          staff.individual_percentage >= 5 &&
          !["s99999999", "s99999999998"].includes(staff.staff_pin)
      );

    const maxPercentage = Math.max(
      ...filteredData.map((staff) => staff.individual_percentage)
    );

    const ranges: number[] = [];
    for (let i = 5; i <= maxPercentage; i += 10) {
      ranges.push(i);
    }
    ranges.push(maxPercentage);

    let staffCountsInRanges = ranges.map((range, index) => {
      const nextRange = ranges[index + 1] || maxPercentage + 1;
      return filteredData.filter(
        (staff) =>
          staff.individual_percentage >= range &&
          staff.individual_percentage < nextRange
      ).length;
    });

    for (let i = staffCountsInRanges.length - 1; i > 0; i--) {
      while (staffCountsInRanges[i] < 3 && i > 0) {
        staffCountsInRanges[i - 1] += staffCountsInRanges[i];
        staffCountsInRanges.splice(i, 1);
        ranges.splice(i, 1);
      }
    }

    staffCountsInRanges[staffCountsInRanges.length - 1] = filteredData.filter(
      (staff) => staff.individual_percentage >= ranges[ranges.length - 1]
    ).length;

    const lineData = {
      labels: ranges
        .slice(0, staffCountsInRanges.length)
        .map((range, index) => {
          const nextRange = ranges[index + 1] || maxPercentage;
          return `${range}% - ${nextRange}%`;
        }),
      datasets: [
        {
          label: "Количество сотрудников",
          data: staffCountsInRanges,
          fill: false,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.2)",
          tension: 0.1,
          pointBackgroundColor: "#3b82f6",
          pointBorderColor: "#fff",
          pointHoverBackgroundColor: "#ef4444",
          pointHoverBorderColor: "#fff",
          pointRadius: 6,
          pointHoverRadius: 8,
          pointStyle: "circle",
        },
      ],
    };

    return { lineData, ranges, staffCountsInRanges, maxPercentage };
  }, [stats]);

  const chartOptions = useMemo(
    () => ({
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: "rgba(128, 128, 128, 0.2)",
          },
          ticks: {
            color: "#F87171",
            font: {
              size: 16,
              weight: "bold" as const,
            },
          },
          title: {
            display: true,
            text: "Количество сотрудников",
            font: {
              size: 16,
              weight: "bold" as const,
              color: "#fff",
            },
          },
        },
        x: {
          ticks: {
            display: true,
            color: "#13ad09",
            font: {
              size: 16,
              weight: "bold" as const,
            },
          },
          grid: {
            color: "rgba(128, 128, 128, 0.2)",
          },
          title: {
            display: true,
            text: "Процент времени на работе",
            font: {
              size: 16,
              weight: "bold" as const,
              color: "#fff",
            },
          },
        },
      },
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          callbacks: {
            label: function (context: TooltipItem<"line">) {
              return `Количество: ${context.raw}`;
            },
          },
          backgroundColor: "rgba(0, 0, 0, 0.8)",
          titleFont: {
            size: 18,
            weight: "bold" as const,
            color: "#fff",
          },
          bodyFont: {
            size: 16,
            weight: "bold" as const,
            color: "#fff",
          },
          footerFont: {
            size: 14,
            weight: "bold" as const,
            color: "#fff",
          },
          padding: 10,
          cornerRadius: 3,
        },
      },
    }),
    []
  );

  if (loading) {
    return <LoaderComponent />;
  }

  if (error) {
    return <Notification message={error} type="error" />;
  }

  if (!stats) {
    const message = "Данные не были найдены.";
    return <Notification message={message} type="warning" />;
  }

  if (stats.present_data.length === 0) {
    const formattedDate = formatDate(stats.data_for_date || selectedDate);
    const message = `Данные за ${formattedDate} не были найдены, обратитесь к системному администратору.`;

    return <Notification message={message} type="warning" />;
  }

  const formattedDate = formatDate(stats.data_for_date);

  return (
    <div className="container mx-auto p-4 dark:text-gray-100">
      <h1 className="text-3xl font-bold mb-4 text-center text-gray-200">
        Посещаемость отдела {stats.department_name}
      </h1>
      <h2 className="text-xl mb-6 text-center text-gray-400">
        Посещаемость сотрудников на {formattedDate}
      </h2>
      {stats.total_staff_count === 0 ? (
        <p className="text-center text-gray-400">Нет данных для отображения</p>
      ) : (
        <>
          <div className="bg-white dark:bg-gray-800 shadow-lg rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4 text-center text-gray-700 dark:text-gray-300">
              Процент посещаемости по сотрудникам
            </h2>
            {chartData && (
              <Line data={chartData.lineData} options={chartOptions} />
            )}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              <div className="p-6 bg-white dark:bg-gray-800 shadow-lg rounded-lg text-center">
                <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                  Всего сотрудников
                </h2>
                <p className="text-4xl font-bold text-green-600 dark:text-green-400 mt-2">
                  {stats.total_staff_count}
                </p>
              </div>
              <div className="p-6 bg-white dark:bg-gray-800 shadow-lg rounded-lg text-center">
                <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                  Присутствующие
                </h2>
                <p className="text-4xl font-bold text-blue-600 dark:text-blue-400 mt-2">
                  {stats.present_staff_count}
                </p>
              </div>
              <div className="p-6 bg-white dark:bg-gray-800 shadow-lg rounded-lg text-center">
                <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                  Отсутствующие
                </h2>
                <p className="text-4xl font-bold text-red-600 dark:text-red-400 mt-2">
                  {stats.absent_staff_count}
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {chartData?.ranges
                .slice(0, chartData.staffCountsInRanges.length)
                .map((range, index) => {
                  const nextRange =
                    chartData.ranges[index + 1] || chartData.maxPercentage;
                  return (
                    <div
                      key={index}
                      className="flex flex-col md:flex-row justify-between bg-gray-100 dark:bg-gray-700 p-4 rounded-lg shadow-md"
                    >
                      <span className="font-semibold text-gray-700 dark:text-gray-300">{`${range}% - ${nextRange}%`}</span>
                      <span className="text-gray-900 dark:text-gray-100">{`Сотрудников: ${chartData.staffCountsInRanges[index]}`}</span>
                    </div>
                  );
                })}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
