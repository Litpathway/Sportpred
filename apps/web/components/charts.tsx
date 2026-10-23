"use client";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CalibrationPoint } from "@/types/api";
import { percent } from "@/lib/api";

export function CalibrationChart({points}: {points: CalibrationPoint[]}) {
  const data = [{predicted: 0, ideal: 0}, ...points.map(p => ({...p, ideal: p.predicted})), {predicted: 1, ideal: 1}];
  return <div className="chart" role="img" aria-label="Calibration chart comparing predicted probabilities with observed outcomes"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{top: 10, right: 16, bottom: 0, left: -18}}><CartesianGrid vertical={false} stroke="#29302d" strokeDasharray="3 4"/><XAxis dataKey="predicted" type="number" domain={[0,1]} ticks={[0,.25,.5,.75,1]} tickFormatter={p => percent(p)} tick={{fill: "#818c87", fontSize: 11}} axisLine={false} tickLine={false}/><YAxis domain={[0,1]} ticks={[0,.5,1]} tickFormatter={p => percent(p)} tick={{fill: "#818c87", fontSize: 11}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background: "#171d1a", border: "1px solid #343d37", borderRadius: 8, color: "#e5ece7"}} formatter={v => percent(Number(v), 1)} labelFormatter={v => `Predicted: ${percent(Number(v))}`}/><Line type="linear" dataKey="ideal" stroke="#46534b" strokeDasharray="4 4" dot={false} name="Perfect calibration"/><Line type="monotone" dataKey="observed" connectNulls stroke="#a0e56c" strokeWidth={2.5} dot={{fill: "#a0e56c", r: 3, strokeWidth: 0}} name="Observed"/></LineChart></ResponsiveContainer></div>;
}
export function PerformanceChart({data}: {data: {date: string; accuracy: number; count: number}[]}) {
  return <div className="chart chart-large" role="img" aria-label="Cumulative settled prediction accuracy"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><CartesianGrid vertical={false} stroke="#29302d"/><XAxis dataKey="count" tick={{fill: "#818c87", fontSize: 11}}/><YAxis domain={[0,1]} tickFormatter={p => percent(p)} tick={{fill: "#818c87", fontSize: 11}}/><Tooltip formatter={v => percent(Number(v), 1)} contentStyle={{background: "#171d1a", border: "1px solid #343d37"}}/><Line dataKey="accuracy" stroke="#a0e56c" dot={false} strokeWidth={2}/></LineChart></ResponsiveContainer></div>;
}
