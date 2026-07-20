"use client";

import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Opportunity, SourceBreakdownItem, TimeSeriesPoint, TrendDistribution } from "@/lib/types";

const trendColors = ["#8b5cf6", "#10b981", "#64748b", "#f43f5e"];

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="h-80 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><h2 className="font-semibold">{title}</h2><div className="mt-3 h-64">{children}</div></section>;
}

export function DashboardCharts({ opportunities, timeSeries, distribution, sources }: { opportunities: Opportunity[]; timeSeries: TimeSeriesPoint[]; distribution: TrendDistribution; sources: SourceBreakdownItem[] }) {
  const trendData = Object.entries(distribution).map(([status, value]) => ({ status: status.replace("_count", ""), value }));
  return <div className="grid gap-5 xl:grid-cols-2"><ChartCard title="Problems over time"><ResponsiveContainer width="100%" height="100%"><LineChart data={timeSeries}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="period_start" tickFormatter={(value) => String(value).slice(0, 10)} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="problem_count" stroke="#4f46e5" strokeWidth={2} /></LineChart></ResponsiveContainer></ChartCard><ChartCard title="Top opportunity scores"><ResponsiveContainer width="100%" height="100%"><BarChart data={opportunities}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" hide /><YAxis domain={[0, 1]} /><Tooltip /><Bar dataKey="opportunity_score" fill="#4f46e5" /></BarChart></ResponsiveContainer></ChartCard><ChartCard title="Trend distribution"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={trendData} dataKey="value" nameKey="status" outerRadius={85} label>{trendData.map((_, index) => <Cell key={index} fill={trendColors[index]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer></ChartCard><ChartCard title="Problems by source"><ResponsiveContainer width="100%" height="100%"><BarChart data={sources}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="source" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="problem_count" fill="#0f766e" /></BarChart></ResponsiveContainer></ChartCard></div>;
}
