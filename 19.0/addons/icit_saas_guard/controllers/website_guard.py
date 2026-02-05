import logging

from odoo.http import request

from ..utils import is_admin_subdomain

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.website.controllers.main import Website
    from odoo.http import route

    class WebsiteGuard(Website):
        """Redirect admin subdomain root to the ops dashboard."""

        @route('/', type='http', auth='public', website=True, sitemap=True)
        def index(self, **kw):
            if is_admin_subdomain():
                return request.redirect('/web/database/manager')
            return super().index(**kw)

except ImportError:
    _logger.debug("website module not available — skipping WebsiteGuard")
