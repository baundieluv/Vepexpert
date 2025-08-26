import asyncio
import json
import websockets
import numpy as np
from scipy import signal
import time
import gc
import os
from aiohttp import web
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('emg_server')

# Store connected clients
connected_clients = set()

# Throttle data sending
THROTTLE_INTERVAL_MS = 20  # Send to web clients at most every 20ms (~50fps)
last_web_send_time = {}    # Track last send time per client

# Default filter settings
filter_settings = {
    'notch_enabled': True,
    'low_pass_cutoff': 330.0,  # Hz (default)
    'high_pass_cutoff': 20.0,  # Hz (default)
}

# Sample rate (Hz) - should match the ESP32 sample rate
SAMPLE_RATE = 1650

# Filter design parameters
FILTER_ORDER = 4
Q_FACTOR = 30.0  # Q factor for notch filter

# Filter state variables for both channels (for continuous filtering)
# Channel 1
notch_zi_ch1 = None
lp_zi_ch1 = None
hp_zi_ch1 = None

# Channel 2
notch_zi_ch2 = None
lp_zi_ch2 = None
hp_zi_ch2 = None

# Filter coefficients
notch_b, notch_a = None, None
lp_b, lp_a = None, None
hp_b, hp_a = None, None

# MPU6050 data
has_mpu_data = False
pitch_angle = 0.0
roll_angle = 0.0

# Data buffers for batching
emg_data_buffer = []
MAX_BUFFER_SIZE = 50  # Maximum number of data points to buffer

# Periodic garbage collection to prevent memory leaks
gc_counter = 0
GC_INTERVAL = 1000  # Run garbage collection every 1000 messages

# Initialize filters
def initialize_filters():
    global notch_b, notch_a, lp_b, lp_a, hp_b, hp_a
    global notch_zi_ch1, lp_zi_ch1, hp_zi_ch1
    global notch_zi_ch2, lp_zi_ch2, hp_zi_ch2
    
    # Design notch filter (60Hz)
    notch_b, notch_a = design_notch_filter(60.0, SAMPLE_RATE, Q_FACTOR)
    
    # Design bandpass filter
    (lp_b, lp_a), (hp_b, hp_a) = design_bandpass_filter(
        filter_settings['high_pass_cutoff'], 
        filter_settings['low_pass_cutoff'], 
        SAMPLE_RATE, 
        FILTER_ORDER
    )
    
    # Initialize filter states for channel 1
    notch_zi_ch1 = signal.lfilter_zi(notch_b, notch_a)
    lp_zi_ch1 = signal.lfilter_zi(lp_b, lp_a)
    hp_zi_ch1 = signal.lfilter_zi(hp_b, hp_a)
    
    # Initialize filter states for channel 2
    notch_zi_ch2 = signal.lfilter_zi(notch_b, notch_a)
    lp_zi_ch2 = signal.lfilter_zi(lp_b, lp_a)
    hp_zi_ch2 = signal.lfilter_zi(hp_b, hp_a)

# Design filter functions
def design_notch_filter(freq, sample_rate, Q):
    """Design a notch filter to remove power line interference"""
    b, a = signal.iirnotch(freq, Q, sample_rate)
    return b, a

def design_bandpass_filter(low_freq, high_freq, sample_rate, order):
    """Design a bandpass filter using low-pass and high-pass filters"""
    nyquist = 0.5 * sample_rate
    low = high_freq / nyquist
    high = low_freq / nyquist
    
    if low >= 1.0:
        low = 0.99
    
    # Design Butterworth filters
    b_low, a_low = signal.butter(order, low, btype='low')
    b_high, a_high = signal.butter(order, high, btype='high')
    
    return (b_low, a_low), (b_high, a_high)

async def process_emg_data(data_ch1, data_ch2):
    """Apply digital filters to both EMG data channels"""
    global notch_zi_ch1, lp_zi_ch1, hp_zi_ch1
    global notch_zi_ch2, lp_zi_ch2, hp_zi_ch2
    
    # Convert to float if necessary
    if isinstance(data_ch1, int):
        data_ch1 = float(data_ch1)
    if isinstance(data_ch2, int):
        data_ch2 = float(data_ch2)
    
    # Process channel 1
    filtered_ch1 = data_ch1
    if filter_settings['notch_enabled']:
        filtered_ch1_notch, notch_zi_ch1 = signal.lfilter(notch_b, notch_a, [filtered_ch1], zi=notch_zi_ch1)
        filtered_ch1 = filtered_ch1_notch[0]
    
    filtered_ch1_lp, lp_zi_ch1 = signal.lfilter(lp_b, lp_a, [filtered_ch1], zi=lp_zi_ch1)
    filtered_ch1_hp, hp_zi_ch1 = signal.lfilter(hp_b, hp_a, [filtered_ch1_lp[0]], zi=hp_zi_ch1)
    
    # Process channel 2
    filtered_ch2 = data_ch2
    if filter_settings['notch_enabled']:
        filtered_ch2_notch, notch_zi_ch2 = signal.lfilter(notch_b, notch_a, [filtered_ch2], zi=notch_zi_ch2)
        filtered_ch2 = filtered_ch2_notch[0]
    
    filtered_ch2_lp, lp_zi_ch2 = signal.lfilter(lp_b, lp_a, [filtered_ch2], zi=lp_zi_ch2)
    filtered_ch2_hp, hp_zi_ch2 = signal.lfilter(hp_b, hp_a, [filtered_ch2_lp[0]], zi=hp_zi_ch2)
    
    # Return both raw and filtered data for both channels
    return data_ch1, filtered_ch1_hp[0], data_ch2, filtered_ch2_hp[0]

async def update_filter_settings(settings):
    """Update filter settings and redesign filters"""
    global filter_settings, notch_b, notch_a, lp_b, lp_a, hp_b, hp_a
    
    # Update settings
    filter_settings.update(settings)
    
    # Redesign filters and reset states
    initialize_filters()
    
    logger.info(f"Filters updated: LP={filter_settings['low_pass_cutoff']}Hz, HP={filter_settings['high_pass_cutoff']}Hz, Notch={'enabled' if filter_settings['notch_enabled'] else 'disabled'}")

async def send_to_web_clients(data):
    """Send data to web clients with throttling"""
    if not connected_clients:
        return
    
    current_time = time.time() * 1000  # Current time in milliseconds
    
    # Convert data to JSON string once
    json_data = json.dumps(data)
    
    # Send to each client with throttling
    sending_tasks = []
    for client in connected_clients:
        client_id = id(client)
        
        # Check if we should throttle for this client
        if client_id in last_web_send_time:
            time_since_last_send = current_time - last_web_send_time[client_id]
            if time_since_last_send < THROTTLE_INTERVAL_MS:
                continue
        
        # Update last send time
        last_web_send_time[client_id] = current_time
        
        # Add send task
        sending_tasks.append(client.send(json_data))
    
    # Execute all send tasks concurrently if there are any
    if sending_tasks:
        await asyncio.gather(*sending_tasks, return_exceptions=True)

async def process_data_buffer():
    """Process and clear the data buffer periodically"""
    global emg_data_buffer
    
    # Skip if buffer is empty
    if not emg_data_buffer:
        return
    
    # Process all buffered data
    for data in emg_data_buffer:
        await send_to_web_clients(data)
    
    # Clear buffer
    emg_data_buffer.clear()

async def handle_esp32_connection(websocket):
    """Handle WebSocket connection from ESP32"""
    global has_mpu_data, pitch_angle, roll_angle, gc_counter, emg_data_buffer
    
    # Get client information
    client_info = websocket.remote_address if hasattr(websocket, 'remote_address') else "Unknown"
    
    # Log ESP32 connection event
    logger.info(f"\n==== ESP32 CONNECTED ====")
    logger.info(f"Remote address: {client_info}")
    logger.info(f"Time: {asyncio.get_event_loop().time()}")
    logger.info("=========================\n")
    
    # Notify all web clients about ESP32 connection
    if connected_clients:
        connection_event = {
            'type': 'esp32_status',
            'status': 'connected',
            'timestamp': asyncio.get_event_loop().time(),
            'clientInfo': str(client_info)
        }
        await send_to_web_clients(connection_event)
    
    # Create a buffer processing task
    buffer_task = asyncio.create_task(buffer_processor(100))  # Process buffer every 100ms
    
    try:
        async for message in websocket:
            try:
                # Increment GC counter and run garbage collection if needed
                gc_counter += 1
                if gc_counter >= GC_INTERVAL:
                    gc_counter = 0
                    gc.collect()
                
                # Check if it's a statistics message or raw data
                if message.startswith("STATS"):
                    # Process statistics message
                    parts = message.split(",")
                    if len(parts) == 8:  # STATS,rms1,rms2,mean1,mean2,imbalance,pitch,roll
                        has_mpu_data = True
                        pitch_angle = float(parts[6])
                        roll_angle = float(parts[7])
                        
                        stats_data = {
                            'type': 'emg_stats',
                            'rms1': float(parts[1]),
                            'rms2': float(parts[2]),
                            'mean1': float(parts[3]),
                            'mean2': float(parts[4]),
                            'imbalance': float(parts[5]),
                            'pitch': pitch_angle,
                            'roll': roll_angle
                        }
                        
                        # Send statistics directly (no buffering for stats)
                        await send_to_web_clients(stats_data)
                        
                    elif len(parts) == 6:  # STATS,rms1,rms2,mean1,mean2,imbalance (no MPU)
                        has_mpu_data = False
                        stats_data = {
                            'type': 'emg_stats',
                            'rms1': float(parts[1]),
                            'rms2': float(parts[2]),
                            'mean1': float(parts[3]),
                            'mean2': float(parts[4]),
                            'imbalance': float(parts[5])
                        }
                        
                        # Send statistics directly
                        await send_to_web_clients(stats_data)
                        
                else:
                    # Process raw EMG data (comma-separated values for both channels + optional MPU data)
                    parts = message.split(",")
                    if len(parts) == 4:  # EMG1,EMG2,pitch,roll (with MPU)
                        data_ch1 = float(parts[0])
                        data_ch2 = float(parts[1])
                        pitch_angle = float(parts[2])
                        roll_angle = float(parts[3])
                        has_mpu_data = True
                        
                        # Process the data (apply filters)
                        raw_ch1, filtered_ch1, raw_ch2, filtered_ch2 = await process_emg_data(data_ch1, data_ch2)
                        
                        # Create EMG data object
                        emg_data = {
                            'type': 'emg_data',
                            'raw1': raw_ch1,
                            'filtered1': filtered_ch1,
                            'raw2': raw_ch2,
                            'filtered2': filtered_ch2,
                            'pitch': pitch_angle,
                            'roll': roll_angle
                        }
                        
                        # Add to buffer instead of sending immediately
                        emg_data_buffer.append(emg_data)
                        
                        # Limit buffer size
                        if len(emg_data_buffer) > MAX_BUFFER_SIZE:
                            # Keep only the most recent data points
                            emg_data_buffer = emg_data_buffer[-MAX_BUFFER_SIZE:]
                            
                    elif len(parts) == 2:  # EMG1,EMG2 (no MPU)
                        data_ch1 = float(parts[0])
                        data_ch2 = float(parts[1])
                        has_mpu_data = False
                        
                        # Process the data (apply filters)
                        raw_ch1, filtered_ch1, raw_ch2, filtered_ch2 = await process_emg_data(data_ch1, data_ch2)
                        
                        # Create EMG data object
                        emg_data = {
                            'type': 'emg_data',
                            'raw1': raw_ch1,
                            'filtered1': filtered_ch1,
                            'raw2': raw_ch2,
                            'filtered2': filtered_ch2
                        }
                        
                        # Add to buffer
                        emg_data_buffer.append(emg_data)
                        
                        # Limit buffer size
                        if len(emg_data_buffer) > MAX_BUFFER_SIZE:
                            emg_data_buffer = emg_data_buffer[-MAX_BUFFER_SIZE:]
                            
            except ValueError as e:
                logger.error(f"Invalid data from ESP32: {message}")
                logger.error(f"Error: {e}")
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"\n==== ESP32 DISCONNECTED ====")
        logger.info(f"Remote address: {client_info}")
        logger.info(f"Time: {asyncio.get_event_loop().time()}")
        logger.info("============================\n")
        
        # Notify all web clients about ESP32 disconnection
        if connected_clients:
            disconnection_event = {
                'type': 'esp32_status',
                'status': 'disconnected',
                'timestamp': asyncio.get_event_loop().time(),
                'clientInfo': str(client_info)
            }
            await send_to_web_clients(disconnection_event)
    finally:
        # Cancel buffer processing task
        buffer_task.cancel()
        try:
            await buffer_task
        except asyncio.CancelledError:
            pass

async def buffer_processor(interval_ms):
    """Process the buffer at regular intervals"""
    try:
        while True:
            await process_data_buffer()
            await asyncio.sleep(interval_ms / 1000)  # Convert ms to seconds
    except asyncio.CancelledError:
        # Final processing of any remaining data
        await process_data_buffer()
        raise

async def handle_web_client(websocket):
    """Handle WebSocket connection from web clients"""
    # Add client to the set
    connected_clients.add(websocket)
    logger.info(f"Web client connected. Total clients: {len(connected_clients)}")
    
    # Send MPU status to the client
    await websocket.send(json.dumps({
        'type': 'mpu_status',
        'available': has_mpu_data
    }))
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle filter settings update
                if data['type'] == 'filter_settings':
                    await update_filter_settings({
                        'notch_enabled': data['notch_enabled'],
                        'low_pass_cutoff': data['low_pass_cutoff'],
                        'high_pass_cutoff': data['high_pass_cutoff']
                    })
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Invalid message from web client: {message}")
                logger.error(f"Error: {e}")
    except websockets.exceptions.ConnectionClosed:
        logger.info("Web client disconnected")
    finally:
        # Remove client from the set
        if websocket in connected_clients:
            connected_clients.remove(websocket)
            
            # Clean up last send time
            client_id = id(websocket)
            if client_id in last_web_send_time:
                del last_web_send_time[client_id]
                
        logger.info(f"Web client disconnected. Total clients: {len(connected_clients)}")

# Health check endpoint
async def health_check(request):
    return web.Response(text="Server is running", status=200)

# Route handler for root path (/) - serves index.html
async def index_handler(request):
    static_path = os.path.join(os.path.dirname(__file__), 'static')
    index_path = os.path.join(static_path, 'index.html')
    
    # Check if index.html exists
    if os.path.exists(index_path):
        logger.info(f"Serving index.html from {index_path}")
        return web.FileResponse(index_path)
    else:
        logger.warning(f"index.html not found at {index_path}")
        return web.Response(
            text="<html><body><h1>Welcome to Vepexpert EMG Server</h1><p>index.html not found in static directory.</p></body></html>",
            content_type='text/html'
        )

# Static file server
def setup_static_server():
    app = web.Application()
    
    # Add health check endpoint
    app.router.add_get('/health', health_check)
    
    # Define static directory path
    static_path = os.path.join(os.path.dirname(__file__), 'static')
    logger.info(f"Setting up static file server from: {static_path}")
    
    # Check if static directory exists
    if not os.path.exists(static_path):
        logger.warning(f"Static directory not found at {static_path}, creating empty directory")
        os.makedirs(static_path, exist_ok=True)
    
    # List files in static directory for debugging
    try:
        files = os.listdir(static_path)
        logger.info(f"Files in static directory: {files}")
    except Exception as e:
        logger.error(f"Error listing files in static directory: {e}")
    
    # Special case for root path - serve index.html
    app.router.add_get('/', index_handler)
    
    # Add static file serving
    app.add_routes([web.static('/', static_path)])
    
    return app

async def main():
    try:
        # Get ports from environment or use defaults
        web_client_port = int(os.environ.get('WEB_CLIENT_PORT', 8080))
        esp32_port = int(os.environ.get('ESP32_PORT', 8081))
        http_port = int(os.environ.get('HTTP_PORT', 8000))
        
        # Initialize filters
        initialize_filters()
        
        # Start WebSocket servers
        esp32_server = await websockets.serve(
            handle_esp32_connection, 
            "0.0.0.0", 
            esp32_port, 
            ping_interval=30,
            ping_timeout=10,
            max_size=None,
            max_queue=32
        )
        
        web_server = await websockets.serve(
            handle_web_client, 
            "0.0.0.0", 
            web_client_port, 
            ping_interval=30,
            ping_timeout=10,
            max_size=None,
            max_queue=32
        )
        
        # Start HTTP server for static files
        app = setup_static_server()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', http_port)
        await site.start()
        
        logger.info("Dual-Channel EMG Server with MPU6050 Support is running")
        logger.info(f"Waiting for ESP32 connection on ws://0.0.0.0:{esp32_port}")
        logger.info(f"Waiting for web clients on ws://0.0.0.0:{web_client_port}")
        logger.info(f"HTTP server for static files running on http://0.0.0.0:{http_port}")
        logger.info(f"Visit http://0.0.0.0:{http_port}/ to access the web interface")
        
        await asyncio.Future()  # Run forever
        
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutdown by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)