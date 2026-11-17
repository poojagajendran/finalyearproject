from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.models.product import Category, Product

SEED_CATEGORIES = [
    {
        "slug": "audio",
        "name": "Wireless Audio & Headphones",
        "description": "High fidelity earbuds, over-ear studio monitors, and portable speakers.",
        "icon": "Headphones"
    },
    {
        "slug": "wearables",
        "name": "Smartwatches & Wearables",
        "description": "Fitness trackers, AMOLED smartwatches, and smart rings.",
        "icon": "Watch"
    },
    {
        "slug": "accessories",
        "name": "Computer & Mobile Accessories",
        "description": "Mechanical keyboards, ergonomic mice, GaN fast chargers, and power banks.",
        "icon": "Keyboard"
    },
    {
        "slug": "tablets",
        "name": "Tablets & E-Readers",
        "description": "Productivity tablets, stylus pens, and glare-free e-readers.",
        "icon": "Tablet"
    }
]

SEED_PRODUCTS = [
    {
        "slug": "boat-rockerz-450",
        "title": "boAt Rockerz 450 Bluetooth On-Ear Headphones",
        "description": "Lightweight wireless on-ear headphones with 40mm dynamic drivers, up to 15 hours playback, and plush padded earcups.",
        "category_slug": "audio",
        "price_paise": 149900,  # ₹1,499.00
        "original_price_paise": 399000,
        "rating": 4.3,
        "reviews_count": 8420,
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 85,
        "brand": "boAt"
    },
    {
        "slug": "oneplus-nord-buds-2",
        "title": "OnePlus Nord Buds 2 TWS In-Ear Earbuds",
        "description": "True wireless earbuds featuring 25dB Active Noise Cancellation, BassWave enhancement algorithm, and 36 hours total battery life.",
        "category_slug": "audio",
        "price_paise": 199900,  # ₹1,999.00
        "original_price_paise": 329900,
        "rating": 4.6,
        "reviews_count": 12450,
        "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 120,
        "brand": "OnePlus"
    },
    {
        "slug": "sony-wh-1000xm5",
        "title": "Sony WH-1000XM5 Wireless Industry-Leading ANC Headphones",
        "description": "Flagship wireless noise-canceling headphones with Auto NC Optimizer, 8 microphones, LDAC Hi-Res audio, and 30-hour battery life.",
        "category_slug": "audio",
        "price_paise": 2699000,  # ₹26,990.00
        "original_price_paise": 3499000,
        "rating": 4.8,
        "reviews_count": 3120,
        "image_url": "https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 40,
        "brand": "Sony"
    },
    {
        "slug": "noise-colorfit-pro-4",
        "title": "Noise ColorFit Pro 4 Advanced Bluetooth Calling Smartwatch",
        "description": "1.72-inch TFT display, Tru Sync Bluetooth calling, 100 sports modes, continuous heart rate and SpO2 tracking.",
        "category_slug": "wearables",
        "price_paise": 249900,  # ₹2,499.00
        "original_price_paise": 599900,
        "rating": 4.2,
        "reviews_count": 5900,
        "image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 90,
        "brand": "Noise"
    },
    {
        "slug": "apple-airpods-pro-2",
        "title": "Apple AirPods Pro (2nd Generation) with MagSafe USB-C Case",
        "description": "Up to 2x more Active Noise Cancellation, Adaptive Audio, Personalized Spatial Audio with dynamic head tracking, and dust, sweat, and water resistance.",
        "category_slug": "audio",
        "price_paise": 2099900,  # ₹20,999.00
        "original_price_paise": 2490000,
        "rating": 4.9,
        "reviews_count": 9480,
        "image_url": "https://images.unsplash.com/photo-1600294037681-c80b4cb5b434?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 30,
        "brand": "Apple"
    },
    {
        "slug": "logitech-mx-master-3s",
        "title": "Logitech MX Master 3S Performance Wireless Mouse",
        "description": "Quiet clicks, 8K DPI track-on-glass sensor, MagSpeed electromagnetic scrolling, USB-C fast charging, and customizable thumb buttons.",
        "category_slug": "accessories",
        "price_paise": 899500,  # ₹8,995.00
        "original_price_paise": 1099500,
        "rating": 4.8,
        "reviews_count": 2100,
        "image_url": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 45,
        "brand": "Logitech"
    },
    {
        "slug": "keychron-k2-wireless",
        "title": "Keychron K2 V2 Wireless Mechanical Keyboard (RGB Backlit)",
        "description": "Compact 75% layout, hot-swappable Gateron G Pro Brown switches, connects up to 3 devices via Bluetooth 5.1, Mac and Windows compatible.",
        "category_slug": "accessories",
        "price_paise": 749900,  # ₹7,499.00
        "original_price_paise": 999900,
        "rating": 4.7,
        "reviews_count": 1420,
        "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 35,
        "brand": "Keychron"
    },
    {
        "slug": "anker-65w-gan-charger",
        "title": "Anker 735 GaNPrime 65W 3-Port Fast Wall Charger",
        "description": "Charge 3 devices simultaneously with 2 USB-C ports and 1 USB-A port. PowerIQ 4.0 dynamic power distribution and ActiveShield 2.0 temperature protection.",
        "category_slug": "accessories",
        "price_paise": 299900,  # ₹2,999.00
        "original_price_paise": 499900,
        "rating": 4.6,
        "reviews_count": 3310,
        "image_url": "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 60,
        "brand": "Anker"
    },
    {
        "slug": "xiaomi-power-bank-3i-20000",
        "title": "Xiaomi 20000mAh 18W Fast Charging Power Bank 3i",
        "description": "Triple port output, dual input (Micro-USB and Type-C), advanced 12-layer circuit protection, and smart power management for low-power devices.",
        "category_slug": "accessories",
        "price_paise": 179900,  # ₹1,799.00
        "original_price_paise": 249900,
        "rating": 4.4,
        "reviews_count": 18200,
        "image_url": "https://images.unsplash.com/photo-1609592424368-2ec25cf398b6?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 110,
        "brand": "Xiaomi"
    },
    {
        "slug": "kindle-paperwhite-16gb",
        "title": "Kindle Paperwhite (16 GB) 6.8-inch Glare-Free Display",
        "description": "Adjustable warm light, up to 10 weeks of battery life, 20% faster page turns, and waterproof (IPX8) design for reading by the pool.",
        "category_slug": "tablets",
        "price_paise": 1499900,  # ₹14,999.00
        "original_price_paise": 1699900,
        "rating": 4.7,
        "reviews_count": 6700,
        "image_url": "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=600&auto=format&fit=crop&q=80",
        "stock_quantity": 25,
        "brand": "Amazon"
    }
]

async def seed_initial_catalog(db: AsyncSession) -> None:
    """Seed categories and products if not already seeded"""
    cat_check = await db.execute(select(Category))
    if not cat_check.first():
        for cat in SEED_CATEGORIES:
            db.add(Category(**cat))
        await db.flush()

    prod_check = await db.execute(select(Product))
    if not prod_check.first():
        for prod in SEED_PRODUCTS:
            db.add(Product(**prod))
        await db.commit()
