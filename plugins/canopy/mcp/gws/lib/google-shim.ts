/**
 * Drop-in shim that preserves the `import { google } from 'googleapis'`
 * call shape while pulling from the per-API subpackages instead of the
 * 194 MB `googleapis` meta-package (cuts node_modules by ~190 MB on every
 * plugin install).
 *
 * Call sites keep using `google.drive({ version: 'v3', auth })`,
 * `new google.auth.GoogleAuth(…)`, etc. — only the import path changes.
 * Same wire protocol, same generated types, just scoped to the APIs the
 * gws server actually uses (Drive, Docs, Sheets, Slides, Forms) plus the
 * auth client.
 *
 * NOTE: `google-auth-library` is pinned EXACTLY (not ^) in package.json to
 * the version `googleapis-common` pins, so npm dedupes to a single copy.
 * Two copies produce nominal-type (#private) mismatches under tsc.
 */
import { drive } from '@googleapis/drive';
import { docs } from '@googleapis/docs';
import { sheets } from '@googleapis/sheets';
import { slides } from '@googleapis/slides';
import { forms } from '@googleapis/forms';
import * as auth from 'google-auth-library';

export const google = { drive, docs, sheets, slides, forms, auth };
