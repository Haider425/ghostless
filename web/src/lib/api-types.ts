/*
  Names for the API's types, safe to import anywhere (server or browser):
  this file has no runtime code, only types generated from the API.
*/

import type { components, operations } from "./api-schema";

type Schemas = components["schemas"];
export type Job = Schemas["JobSummary"];
export type JobDetail = Schemas["JobDetail"];
export type JobPage = Schemas["JobPage"];
export type Company = Schemas["Company"];
export type CompanyDetail = Schemas["CompanyDetail"];
export type CompanyPage = Schemas["CompanyPage"];
export type CompanyName = Schemas["CompanyName"];
export type WeekCount = Schemas["WeekCount"];
export type Stats = Schemas["Stats"];
export type SkillCount = Schemas["SkillCount"];
export type GapReport = Schemas["GapReport"];
export type CalendarEntry = Schemas["CalendarEntry"];
export type User = Schemas["User"];
export type Settings = Schemas["Settings"];
export type OAuthProvider = NonNullable<Schemas["User"]["sign_in_providers"]>[number];
export type Analysis = Schemas["Analysis"];
export type Profile = Schemas["ProfileModel"];
export type ResumeCheck = Schemas["CheckModel"];
export type Match = Schemas["MatchModel"];
export type Recommendation = Schemas["Recommendation"];
export type RecommendationPage = Schemas["RecommendationPage"];
export type ResumeSummary = Schemas["ResumeSummary"];
export type StoredResume = Schemas["StoredResume"];
export type ResumeDocument = Schemas["ResumeDocument"];
export type AIStatus = Schemas["AIStatus"];
export type AIFeedback = Schemas["AIFeedbackOut"];
export type AdminOverview = Schemas["Overview"];
export type DayStats = Schemas["DayStats"];
export type PathCount = Schemas["PathCount"];
export type AdminUserPage = Schemas["UserPage"];
export type ReportRow = Schemas["ReportRow"];
export type ErrorRow = Schemas["ErrorRow"];
export type RunRow = Schemas["RunRow"];
export type SavedEntry = Schemas["SavedJob"];
export type ApplicationStatus = SavedEntry["status"];
export type Application = Schemas["Application"];
export type Level = Job["level"];
export type RoleType = Job["role_type"];
export type GhostRisk = NonNullable<Job["signals"]["risk"]>;
export type JobQuery = NonNullable<operations["list_jobs_jobs_get"]["parameters"]["query"]>;
export type SkillQuery = NonNullable<operations["top_skills_skills_top_get"]["parameters"]["query"]>;
export type GapQuery = operations["skills_gap_skills_gap_get"]["parameters"]["query"];
export type CompanyListQuery = NonNullable<operations["company_list_company_list_get"]["parameters"]["query"]>;
export type CompanyNamesQuery = NonNullable<operations["company_names_company_names_get"]["parameters"]["query"]>;
export type CalendarQuery = NonNullable<operations["calendar_calendar_get"]["parameters"]["query"]>;

