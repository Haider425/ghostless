"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, attempt, authedClient } from "@/lib/api";
import { clearSessionCookie, sessionToken, visitorHeaders } from "@/lib/session";
import { finishSignIn, safeNext } from "@/lib/signin";

/*
  Sign-up, sign-in and account actions. Forms post here (they work without
  JavaScript too); errors come back as a message for the form to show.
*/

export interface FormState {
  error?: string;
  message?: string;
  fields?: Record<string, string>;
}

async function client(token?: string) {
  return authedClient(token ?? (await sessionToken()), await visitorHeaders());
}

function field(form: FormData, name: string, max = 300): string {
  const value = form.get(name);
  return typeof value === "string" ? value.slice(0, max) : "";
}

export async function signUp(_: FormState, form: FormData): Promise<FormState> {
  const email = field(form, "email", 254).trim();
  const name = field(form, "name", 80).trim();
  const password = field(form, "password", 256);
  if (form.get("terms") !== "on") {
    return { error: "Please agree to the terms and privacy policy to create an account.", fields: { email, name } };
  }
  const result = await attempt(api.signup(await client(""), { email, password, name: name || null }));
  if (!result.ok) return { error: result.message, fields: { email, name } };
  await finishSignIn(result.data.user, result.data.token);
  redirect(safeNext(field(form, "next")) === "/" ? "/account?welcome=1" : safeNext(field(form, "next")));
}

export async function signIn(_: FormState, form: FormData): Promise<FormState> {
  const email = field(form, "email", 254).trim();
  const result = await attempt(api.login(await client(""), { email, password: field(form, "password", 256) }));
  if (!result.ok) return { error: result.message, fields: { email } };
  await finishSignIn(result.data.user, result.data.token);
  redirect(safeNext(field(form, "next")));
}

export async function signOut(): Promise<void> {
  const token = await sessionToken();
  if (token) await api.logout(await client(token));
  await clearSessionCookie();
  redirect("/");
}

export async function forgotPassword(_: FormState, form: FormData): Promise<FormState> {
  const email = field(form, "email", 254).trim();
  const result = await attempt(api.forgotPassword(await client(""), email));
  if (!result.ok) return { error: result.message, fields: { email } };
  return { message: result.data.detail };
}

export async function resetPassword(_: FormState, form: FormData): Promise<FormState> {
  const result = await attempt(api.resetPassword(await client(""), field(form, "token", 200), field(form, "password", 256)));
  if (!result.ok) return { error: result.message };
  await finishSignIn(result.data.user, result.data.token);
  redirect("/account?reset=1");
}

export async function verifyEmail(_: FormState, form: FormData): Promise<FormState> {
  const result = await attempt(api.verifyEmail(await client(""), field(form, "token", 200)));
  if (!result.ok) return { error: result.message };
  return { message: "Your email is confirmed. Thanks!" };
}

export async function resendVerification(_: FormState): Promise<FormState> {
  const result = await attempt(api.resendVerification(await client()));
  return result.ok ? { message: result.data.detail } : { error: result.message };
}

export async function updateName(_: FormState, form: FormData): Promise<FormState> {
  const result = await attempt(api.updateProfile(await client(), field(form, "name", 80).trim() || null));
  return result.ok ? { message: "Saved." } : { error: result.message };
}

export async function changePassword(_: FormState, form: FormData): Promise<FormState> {
  const next = field(form, "new_password", 256);
  if (next !== field(form, "confirm_password", 256)) return { error: "The new passwords don't match." };
  const result = await attempt(api.changePassword(await client(), field(form, "current_password", 256), next));
  return result.ok ? { message: result.data.detail } : { error: result.message };
}

export async function signOutEverywhere(_: FormState): Promise<FormState> {
  const result = await attempt(api.logoutEverywhere(await client()));
  return result.ok ? { message: result.data.detail } : { error: result.message };
}

export async function deleteAccount(_: FormState, form: FormData): Promise<FormState> {
  if (field(form, "confirm").trim().toLowerCase() !== "delete my account") {
    return { error: "Type “delete my account” to confirm." };
  }
  const result = await attempt(api.deleteAccount(await client(), field(form, "password", 256)));
  if (!result.ok) return { error: result.message };
  await clearSessionCookie();
  redirect("/?deleted=1");
}

/** Remove a Google or GitHub sign-in from the account. */
export async function unlinkProvider(_: FormState, form: FormData): Promise<FormState> {
  const provider = field(form, "provider", 20);
  if (provider !== "google" && provider !== "github") return { error: "That sign-in method isn't recognized." };
  const result = await attempt(api.unlinkProvider(await client(), provider));
  if (!result.ok) return { error: result.message };
  revalidatePath("/account");
  return { message: result.data.detail };
}
