<?php
// The settings row Snipe-IT's setup wizard writes (SetupController), so the API works without the wizard.
use App\Models\Setting;
if (Setting::count() === 0) {
    $s = new Setting;
    $s->site_name = 'Harbor Trading (SAMPLE)';
    $s->alert_email = 'admin@harbor-trading.example';
    $s->alerts_enabled = 0;
    $s->pwd_secure_min = 10;
    $s->brand = 1;
    $s->link_light_color = '#296282';
    $s->link_dark_color = '#296282';
    $s->nav_link_color = '#FFFFFF';
    $s->locale = 'en-US';
    $s->default_currency = 'SAR';
    $s->created_by = 1;
    $s->email_domain = 'harbor-trading.example';
    $s->email_format = 'firstname.lastname';
    $s->next_auto_tag_base = 1;
    $s->auto_increment_assets = 0;
    $s->zerofill_count = 0;
    $s->audit_interval = 12;
    $s->audit_warning_days = 30;
    $s->save();
}
echo 'settings '.Setting::count();
