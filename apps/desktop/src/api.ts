export const API_BASE = import.meta.env.VITE_AIVATAR_API ?? "http://127.0.0.1:8765";
export async function api<T>(path:string,init?:RequestInit):Promise<T>{const res=await fetch(`${API_BASE}${path}`,{...init,headers:{"Content-Type":"application/json",...(init?.headers??{})}});if(!res.ok)throw new Error(await res.text());return res.json()}
export type Project={id:string;name:string;state:string;expected_duration:number;final_duration?:number;presenter_target:number;presenter_actual:number;actual_cost_usd:number;created_at:string};
export type Channel={id:string;name:string;style_preset:string};
export type ActivationCheck={id:string;label:string;ready:boolean;required:boolean;detail:string;action?:string|null};
export type ActivationStatus={ready_for_real_reference_test:boolean;readiness_percent:number;required_ready:number;required_total:number;blockers:ActivationCheck[];checks:ActivationCheck[];next_milestone:string;reference_profile:string;safety_boundary:string};
export type ReferenceProfile={id:string;name:string;status:string;source:string;editorial:{presenter_target:number;visual_density:number;preferred_scene_seconds:{min:number;target:number;max:number}};composition:{split_default:string;pip_enabled:boolean};visuals:{selection_order:string[];ltx_policy:string};output:{aspect_ratio:string;resolution:string;fps:number;format:string};validation:{note:string}};
