-- Run once in the SQL Editor of your own new RoadProof Supabase project.
-- All application access comes from the Streamlit server. There are no public table policies.
begin;

create table if not exists public.rp_reports (
  id text primary key check (id ~ '^RP-[A-F0-9]{10}$'),
  token_hash text not null unique check (token_hash ~ '^[a-f0-9]{64}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  lat double precision not null check (lat between -90 and 90),
  lon double precision not null check (lon between -180 and 180),
  location text not null,
  description text not null check (length(description) between 10 and 2000),
  image_path text not null,
  status text not null default 'Reported' check (status in ('Reported','Under Review','Assigned',
    'Repair in Progress','Repair Claimed Complete','Verification Pending','Verified and Closed','Reopened')),
  ai_status text not null,
  model text not null default 'Not connected',
  analysis_json jsonb not null default '[]'::jsonb,
  measurements_json jsonb,
  cost_json jsonb,
  email text not null default '',
  consent boolean not null default false,
  synthetic boolean not null default false,
  evidence_path text,
  repair_claim_at timestamptz,
  verified_at timestamptz
);

create table if not exists public.rp_history (
  id bigint generated always as identity primary key,
  report_id text not null references public.rp_reports(id),
  created_at timestamptz not null default now(),
  status text not null,
  action text not null,
  note text not null,
  actor text not null,
  evidence_path text
);
create index if not exists rp_history_case on public.rp_history(report_id, id);
create index if not exists rp_reports_date on public.rp_reports(created_at desc);
alter table public.rp_reports enable row level security;
alter table public.rp_history enable row level security;
revoke all on public.rp_reports, public.rp_history from public, anon, authenticated;
revoke all on public.rp_reports, public.rp_history from service_role;
grant select, insert, update on public.rp_reports to service_role;
grant select, insert on public.rp_history to service_role;
grant usage, select on sequence public.rp_history_id_seq to service_role;

-- A private bucket; never add a public-read policy for it.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('roadproof-evidence','roadproof-evidence',false,10485760,array['image/jpeg'])
on conflict(id) do nothing;
do $$ begin
  if exists(select 1 from storage.buckets where id='roadproof-evidence' and public) then
    raise exception 'The roadproof-evidence bucket must be private. Review it before continuing.';
  end if;
end $$;

create or replace function public.rp_create_report(p_report jsonb)
returns text language plpgsql security invoker set search_path = '' as $$
declare existing_id text; image_key text; result_id text;
begin
  if coalesce(p_report->>'token_hash','') !~ '^[a-f0-9]{64}$'
    or coalesce(p_report->>'id','') !~ '^RP-[A-F0-9]{10}$'
    or length(btrim(coalesce(p_report->>'description',''))) not between 10 and 2000
    or coalesce(p_report->>'image_path','') !~ '^supabase://roadproof-evidence/evidence/[a-f0-9]{32}\.jpg$' then
    raise exception 'Invalid report data.';
  end if;
  -- Serialize submissions with the same token, including retries after a lost response.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_report->>'token_hash',0));
  select id into existing_id from public.rp_reports where token_hash=p_report->>'token_hash';
  if existing_id is not null then return existing_id; end if;
  image_key := replace(p_report->>'image_path','supabase://roadproof-evidence/','');
  if not exists(select 1 from storage.objects where bucket_id='roadproof-evidence' and name=image_key) then
    raise exception 'Repair evidence is required.';
  end if;
  result_id := p_report->>'id';
  insert into public.rp_reports (id,token_hash,created_at,lat,lon,location,description,image_path,
      ai_status,model,analysis_json,measurements_json,cost_json,email,consent,synthetic)
  values (result_id,p_report->>'token_hash',coalesce((p_report->>'created_at')::timestamptz,now()),
      (p_report->>'lat')::double precision,(p_report->>'lon')::double precision,
      left(coalesce(nullif(btrim(p_report->>'location'),''),'Selected map location'),160),
      btrim(p_report->>'description'),p_report->>'image_path',p_report->>'ai_status',
      coalesce(p_report->>'model','Not connected'),coalesce(p_report->'analysis_json','[]'::jsonb),
      nullif(p_report->'measurements_json','null'::jsonb),nullif(p_report->'cost_json','null'::jsonb),
      case when coalesce((p_report->>'consent')::boolean,false) then left(coalesce(p_report->>'email',''),254) else '' end,
      coalesce((p_report->>'consent')::boolean,false),coalesce((p_report->>'synthetic')::boolean,false));
  insert into public.rp_history(report_id,status,action,note,actor)
  values (result_id,'Reported','Report recorded','Recorded in RoadProof; no government submission.','Citizen');
  return result_id;
end $$;

create or replace function public.rp_update_case(
  p_id text, p_action text, p_note text, p_value text,
  p_expected text default null, p_attested boolean default false)
returns text language plpgsql security invoker set search_path = '' as $$
declare r public.rp_reports%rowtype; next_status text; event_action text;
  actor_name text := 'Demo administrator'; image_key text;
begin
  if length(btrim(coalesce(p_note,''))) not between 1 and 2000 then
    raise exception 'Add a reason for this change.';
  end if;
  select * into r from public.rp_reports where id=p_id for update;
  if not found then raise exception 'Report not found.'; end if;
  if p_expected is not null and r.status<>p_expected then
    raise exception 'This case changed. Refresh before updating it.';
  end if;
  next_status := r.status;
  if p_action='evidence' then
    if r.status='Verified and Closed' then raise exception 'Reopen this case before replacing evidence.'; end if;
    if coalesce(p_value,'') !~ '^supabase://roadproof-evidence/evidence/[a-f0-9]{32}\.jpg$' then
      raise exception 'Repair evidence is required.';
    end if;
    image_key := replace(p_value,'supabase://roadproof-evidence/','');
    if not exists(select 1 from storage.objects where bucket_id='roadproof-evidence' and name=image_key) then
      raise exception 'Repair evidence is required.';
    end if;
    update public.rp_reports set evidence_path=p_value,updated_at=now() where id=p_id;
    insert into public.rp_history(report_id,status,action,note,actor,evidence_path)
      values(p_id,r.status,'Repair evidence uploaded',btrim(p_note),actor_name,p_value);
    return r.status;
  elsif p_action='status' then
    if not ((r.status='Reported' and p_value='Under Review')
      or (r.status='Under Review' and p_value='Assigned')
      or (r.status='Assigned' and p_value='Repair in Progress')
      or (r.status='Repair in Progress' and p_value='Repair Claimed Complete')
      or (r.status='Repair Claimed Complete' and p_value='Verification Pending')
      or (r.status='Reopened' and p_value in ('Under Review','Assigned','Repair in Progress'))) then
      raise exception 'Use the next workflow stage.';
    end if;
    if p_value in ('Repair Claimed Complete','Verification Pending') and r.evidence_path is null then
      raise exception 'Repair evidence is required.';
    end if;
    next_status := p_value;
    event_action := 'Status changed';
  elsif p_action='review' then
    actor_name := 'Human demo reviewer';
    event_action := p_value;
    if p_value='Mark Verified' then
      if r.status<>'Verification Pending' or r.evidence_path is null or not coalesce(p_attested,false) then
        raise exception 'Verification requires pending evidence and human approval.';
      end if;
      next_status := 'Verified and Closed';
    elsif p_value='Request More Evidence' and r.status in ('Repair Claimed Complete','Verification Pending') then
      next_status := 'Repair in Progress';
    elsif p_value='Reopen Case' and r.status in ('Verified and Closed','Verification Pending','Repair Claimed Complete') then
      next_status := 'Reopened';
    else
      raise exception 'This decision is not available for the current status.';
    end if;
  else
    raise exception 'This decision is not available for the current status.';
  end if;
  update public.rp_reports set status=next_status,updated_at=now(),
    repair_claim_at=case when next_status='Repair Claimed Complete' then now() else repair_claim_at end,
    verified_at=case when next_status='Verified and Closed' then now() else null end where id=p_id;
  insert into public.rp_history(report_id,status,action,note,actor,evidence_path)
    values(p_id,next_status,event_action,btrim(p_note),actor_name,r.evidence_path);
  return next_status;
end $$;

create or replace function public.rp_add_feedback(p_token_hash text,p_note text)
returns void language plpgsql security invoker set search_path = '' as $$
declare r public.rp_reports%rowtype;
begin
  if length(btrim(coalesce(p_note,''))) not between 5 and 2000 then
    raise exception 'Add a reason for this change.';
  end if;
  select * into r from public.rp_reports where token_hash=p_token_hash for update;
  if not found then raise exception 'Tracking access is invalid.'; end if;
  insert into public.rp_history(report_id,status,action,note,actor)
    values(r.id,r.status,'Citizen feedback',btrim(p_note),'Citizen');
end $$;

-- Postgres functions default to PUBLIC execution; explicitly restrict every RPC.
revoke all on function public.rp_create_report(jsonb) from public, anon, authenticated;
revoke all on function public.rp_update_case(text,text,text,text,text,boolean) from public, anon, authenticated;
revoke all on function public.rp_add_feedback(text,text) from public, anon, authenticated;
grant execute on function public.rp_create_report(jsonb) to service_role;
grant execute on function public.rp_update_case(text,text,text,text,text,boolean) to service_role;
grant execute on function public.rp_add_feedback(text,text) to service_role;
commit;
