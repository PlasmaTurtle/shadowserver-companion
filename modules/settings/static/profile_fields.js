/** Shared controlled profile fields. Catalogs and persistence remain owned by each caller. */
export function requireProfileCatalog(catalog) {
  if (!catalog?.agencies?.length || !catalog?.regions?.length || !catalog?.timezones?.length)
    throw new Error('Profile choices could not be loaded. Reopen Settings or setup to try again.');
  return catalog;
}

export function profileInput(esc, prefix, label, name, value = '', options = {}) {
  return `<div class="field ${options.full ? 'full' : ''}"><label for="${prefix}${name}">${label}</label><input id="${prefix}${name}" name="${name}" type="${options.type || 'text'}" value="${esc(value ?? '')}" maxlength="${options.max || 500}" ${options.required ? 'required data-profile-trim-required' : ''} ${options.autocomplete ? `autocomplete="${options.autocomplete}"` : ''}>${options.help ? `<small>${options.help}</small>` : ''}</div>`;
}

export function agencyFields(esc, profile, catalog, prefix, selectId) {
  const agency = catalog.agencies.find((item) => item.name === profile.agency);
  const valid = agency && agency.department === profile.department;
  const review = profile.agency || profile.department;
  return `<div class="field full"><label for="${selectId}">Agency</label><select id="${selectId}" name="agency" required><option value="" ${!valid ? 'selected' : ''}>${review && !valid ? 'Review saved agency and select an approved agency' : 'Select agency'}</option>${catalog.agencies.map((item) => `<option value="${esc(item.name)}" ${valid && agency === item ? 'selected' : ''}>${esc(item.short_name)} — ${esc(item.name)}</option>`).join('')}</select><small>Choose the agency responsible for this workspace. Jurisdiction is selected separately.</small>${review && !valid ? `<p class="notice warn" data-legacy-agency>Saved agency: ${esc(profile.agency || '(empty)')}. Saved department: ${esc(profile.department || '(empty)')}. Select an approved agency to replace these values.</p>` : ''}</div><div class="field full"><label for="${prefix}department">Department / parent organization</label><input id="${prefix}department" name="department" value="${esc(profile.department || '')}" readonly><small>Set by the selected agency.</small></div>`;
}

export function jurisdictionFields(esc, profile, catalog, action) {
  const selected = profile.regions || [];
  const unsupported = selected.filter((name) => !catalog.regions.includes(name));
  return `<fieldset class="full setup-regions profile-jurisdictions"><legend>Report jurisdictions</legend><p class="help">Select the states, District of Columbia or territories you work. Agency identity does not grant report access. Changing scope does not delete existing records.</p><div class="setup-region-grid">${catalog.regions.map((name) => `<label class="checkbox"><input type="checkbox" name="regions" value="${esc(name)}" ${selected.includes(name) ? 'checked' : ''}><span>${esc(name)}</span></label>`).join('')}</div>${unsupported.length ? `<div class="notice warn" data-unsupported-regions><p>Unsupported saved jurisdictions: ${unsupported.map(esc).join(', ')}. Select their supported replacements, then explicitly remove these saved values before saving.</p>${unsupported.map((name) => `<input type="hidden" name="regions" value="${esc(name)}">`).join('')}<button type="button" class="button" data-action="${action}">Remove unsupported saved jurisdictions</button></div>` : ''}</fieldset>`;
}

export function timezoneField(esc, profile, catalog, id) {
  const selected = profile.display_timezone ?? 'America/New_York';
  const known = catalog.timezones.includes(selected);
  return `<div class="field"><label for="${id}">Display timezone</label><select id="${id}" name="display_timezone" required>${!known ? `<option value="" selected>Review saved timezone: ${esc(selected)}</option>` : ''}${catalog.timezones.map((zone) => `<option value="${esc(zone)}" ${zone === selected ? 'selected' : ''}>${esc(zone.replaceAll('_', ' '))}</option>`).join('')}</select><small>Event times retain their original UTC values; timestamps display the selected zone.</small></div>`;
}

export function authorityMarkup(esc, agency) {
  const authority = agency?.authority;
  if (!authority)
    return '<p class="help">Select an approved agency to review its mission and authority.</p>';
  return `<h3>${esc(authority.title)}</h3><p>${esc(authority.purpose_statement)}</p><ul>${(authority.authorities || []).map((item) => `<li><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.citation)}</a> — ${esc(item.description)}</li>`).join('')}</ul><p class="help">These references describe the agency mission. Record the specific connection between this outreach and that mission below.</p>`;
}

export function targetedFields(esc, profile, catalog, prefix, authorityId) {
  const targeted = profile.outreach_mode === 'targeted';
  const agency = catalog.agencies.find((item) => item.name === profile.agency);
  return `<section class="full profile-authority" id="${authorityId}" ${targeted ? '' : 'hidden'}>${authorityMarkup(esc, agency)}</section><div class="field full"><label for="${prefix}targeted_reason">Purpose-specific explanation for targeted outreach</label><textarea id="${prefix}targeted_reason" name="targeted_reason" rows="3" maxlength="2000" ${targeted ? 'required data-profile-trim-required' : ''}>${esc(profile.targeted_reason || '')}</textarea><small>Explain how the specific findings or report type relate to the selected agency's mission and authority. Changing agency requires a new explanation.</small></div>`;
}

export function applyAgencySelection(select, catalog, esc, authorityId) {
  const form = select.closest('form');
  const agency = catalog?.agencies?.find((item) => item.name === select.value);
  const department = form?.querySelector('[name="department"]');
  if (department) department.value = agency?.department || '';
  if (agency) form?.querySelector('[data-legacy-agency]')?.remove();
  const authority = form?.querySelector(`#${authorityId}`);
  if (authority) authority.innerHTML = authorityMarkup(esc, agency);
  const reason = form?.querySelector('[name="targeted_reason"]');
  if (reason) reason.value = '';
}

export function validateProfileFields(form) {
  for (const input of form.querySelectorAll?.('[data-profile-trim-required]') || [])
    input.setCustomValidity(
      input.value.trim() ? '' : 'Enter a value. Blank spaces are not enough.',
    );
  const regions = [...(form.querySelectorAll?.('input[type="checkbox"][name="regions"]') || [])];
  if (regions.length)
    regions[0].setCustomValidity(
      form.querySelector('[data-unsupported-regions]')
        ? 'Remove unsupported saved jurisdictions after selecting their replacements.'
        : regions.some((input) => input.checked)
          ? ''
          : 'Select at least one report jurisdiction.',
    );
}

export function removeUnsupportedRegions(button) {
  const firstRegion = button.closest('fieldset')?.querySelector('input[type="checkbox"]');
  button.closest('[data-unsupported-regions]')?.remove();
  firstRegion?.focus();
}
