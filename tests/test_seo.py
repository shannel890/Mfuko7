from html.parser import HTMLParser
from xml.etree import ElementTree

import pytest

from app import create_app


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.canonical = None
        self.title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'meta':
            key = attributes.get('name') or attributes.get('property')
            if key:
                self.meta[key] = attributes.get('content')
        elif tag == 'link' and attributes.get('rel') == 'canonical':
            self.canonical = attributes.get('href')
        elif tag == 'title':
            self.title = True


@pytest.fixture
def seo_app(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('SECRET_KEY', 'test-only-signing-key')
    monkeypatch.setenv('PUBLIC_SITE_URL', 'https://mfuko.example.test')
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def parse_metadata(response):
    parser = MetadataParser()
    parser.feed(response.get_data(as_text=True))
    return parser


def test_public_pages_are_indexable_and_have_canonical_metadata(seo_app):
    client = seo_app.test_client()
    public_pages = {
        '/': 'https://mfuko.example.test/',
        '/features': 'https://mfuko.example.test/features',
        '/testimonials': 'https://mfuko.example.test/testimonials',
        '/pricing': 'https://mfuko.example.test/pricing',
        '/contact': 'https://mfuko.example.test/contact',
    }

    for path, canonical in public_pages.items():
        response = client.get(path)
        metadata = parse_metadata(response)
        assert response.status_code == 200
        assert metadata.meta['robots'] == 'index, follow'
        assert metadata.meta['description']
        assert metadata.canonical == canonical


def test_sitemap_contains_only_canonical_public_pages(seo_app):
    client = seo_app.test_client()
    robots = client.get('/robots.txt')
    sitemap = client.get('/sitemap.xml')
    root = ElementTree.fromstring(sitemap.data)
    namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    urls = [element.text for element in root.findall(f'{namespace}url/{namespace}loc')]

    assert robots.status_code == 200
    assert 'Sitemap: https://mfuko.example.test/sitemap.xml' in robots.get_data(as_text=True)
    assert urls == [
        'https://mfuko.example.test/',
        'https://mfuko.example.test/features',
        'https://mfuko.example.test/testimonials',
        'https://mfuko.example.test/pricing',
        'https://mfuko.example.test/contact',
    ]


def test_favicon_asset_and_legacy_route(seo_app):
    client = seo_app.test_client()
    redirect_response = client.get('/favicon.ico')
    favicon_response = client.get('/static/favicon.svg')

    assert redirect_response.status_code == 301
    assert redirect_response.headers['Location'].endswith('/static/favicon.svg')
    assert favicon_response.status_code == 200
    assert favicon_response.mimetype == 'image/svg+xml'


def test_account_and_dashboard_pages_are_not_indexable(seo_app):
    client = seo_app.test_client()
    for path in ('/auth/login', '/auth/register', '/tenant/dashboard', '/landlord/dashboard'):
        response = client.get(path)
        assert response.headers['X-Robots-Tag'] == 'noindex, nofollow'
        if path.startswith('/auth/'):
            assert parse_metadata(response).meta['robots'] == 'noindex, nofollow'

    preview_app = create_app()
    preview_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    preview_app.config['VERCEL_ENVIRONMENT'] = 'preview'
    preview_response = preview_app.test_client().get('/')
    preview_metadata = parse_metadata(preview_response)
    assert preview_response.headers['X-Robots-Tag'] == 'noindex, nofollow'
    assert preview_metadata.meta['robots'] == 'noindex, nofollow'
