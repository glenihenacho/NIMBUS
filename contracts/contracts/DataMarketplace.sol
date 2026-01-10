// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title DataMarketplace
 * @dev Upgradeable atomic settlement marketplace for PAT intent signal segments
 *
 * Core mechanism: Single transaction splits payment to all parties
 * - Browser Users receive BID (provider payout)
 * - Broker receives Spread (platform revenue)
 * - Consumer receives data access rights
 *
 * Upgradeable via UUPS pattern:
 * - updateBrokerContract(address) migrates to new implementation
 * - All state preserved across upgrades
 * - Owner-only (Wyoming DAO LLC)
 *
 * Jurisdiction: Wyoming DAO LLC
 */
contract DataMarketplace is
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable
{
    // PAT token contract
    IERC20 public patToken;

    // Market phases (1-4)
    enum Phase { UTILITY, FORWARDS, SYNTHETICS, SPECULATION }
    Phase public currentPhase;

    // Global configuration
    uint256 public brokerMarginBps;     // Basis points (e.g., 3000 = 30%)
    address public brokerWallet;         // Broker revenue recipient

    // Emergency pause
    bool public paused;

    // Segment types
    enum SegmentType {
        PURCHASE_INTENT,
        RESEARCH_INTENT,
        COMPARISON_INTENT,
        ENGAGEMENT_INTENT,
        NAVIGATION_INTENT
    }

    // Segment data (gas-optimized storage packing)
    struct Segment {
        address provider;            // 20 bytes - Original data provider
        SegmentType segmentType;     // 1 byte
        uint8 windowDays;            // 1 byte - Time window in days (max 30)
        uint16 confidenceBps;        // 2 bytes - Confidence score in bps (max 10000)
        bool active;                 // 1 byte - Segment available for purchase
        // --- slot boundary ---
        uint256 askPrice;            // 32 bytes - ASK price in PAT (wei)
        uint256 createdAt;           // 32 bytes - Timestamp
    }

    // Segment registry
    mapping(uint256 => Segment) public segments;
    uint256 public nextSegmentId;

    // Access rights: consumer => segmentId => hasAccess
    mapping(address => mapping(uint256 => bool)) public accessRights;

    // User earnings tracking (for custodial wallet model)
    mapping(address => uint256) public userEarnings;

    // Events
    event SegmentCreated(
        uint256 indexed segmentId,
        address indexed provider,
        SegmentType segmentType,
        uint256 askPrice
    );

    event SegmentPurchased(
        uint256 indexed segmentId,
        address indexed consumer,
        address indexed provider,
        uint256 askPrice,
        uint256 providerPayout,
        uint256 brokerSpread
    );

    event PayoutRecorded(
        address indexed user,
        uint256 amount,
        uint256 indexed segmentId,
        uint256 timestamp
    );

    event Withdrawal(
        address indexed user,
        uint256 amount,
        uint256 timestamp
    );

    event ConfigUpdated(bytes32 indexed paramKey, uint256 value);
    event WalletUpdated(bytes32 indexed paramKey, address wallet);
    event PhaseAdvanced(uint8 newPhase);
    event MarketPaused(bool paused);

    // Contract upgrade event (per HANDOFF spec)
    event BrokerContractUpdated(address indexed oldAddress, address indexed newAddress);

    // Errors
    error MarketPaused();
    error SegmentNotActive();
    error AlreadyHasAccess();
    error InsufficientAllowance();
    error InvalidConfiguration();
    error InsufficientEarnings();

    // Event keys (gas-optimized)
    bytes32 private constant KEY_BROKER_MARGIN = "brokerMargin";
    bytes32 private constant KEY_BROKER_WALLET = "brokerWallet";

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @dev Initialize the contract (replaces constructor for upgradeable pattern)
     * Provider earnings are held in contract and withdrawn by users directly
     */
    function initialize(
        address _patToken,
        address _brokerWallet,
        uint256 _brokerMarginBps
    ) public initializer {
        require(_patToken != address(0), "Invalid PAT token");
        require(_brokerWallet != address(0), "Invalid broker wallet");
        require(_brokerMarginBps <= 5000, "Margin too high");

        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();

        patToken = IERC20(_patToken);
        brokerWallet = _brokerWallet;
        brokerMarginBps = _brokerMarginBps;
        currentPhase = Phase.UTILITY;
    }

    // ============ UUPS Upgrade Authorization ============

    /**
     * @dev Required by UUPS pattern - authorizes upgrade to new implementation
     * This is the updateBrokerContract(address) from HANDOFF spec
     */
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {
        // Emit the event specified in HANDOFF
        emit BrokerContractUpdated(address(this), newImplementation);
    }

    /**
     * @dev Explicit updateBrokerContract function per HANDOFF spec
     * Atomically migrates to new broker contract implementation
     * @param newBrokerContractAddress The new implementation address
     */
    function updateBrokerContract(address newBrokerContractAddress) external onlyOwner {
        require(newBrokerContractAddress != address(0), "Invalid address");
        // UUPS upgrade - calls _authorizeUpgrade internally
        upgradeToAndCall(newBrokerContractAddress, "");
    }

    // ============ Core Functions ============

    /**
     * @dev Create a new segment listing
     */
    function createSegment(
        SegmentType _type,
        uint8 _windowDays,
        uint16 _confidenceBps,
        uint256 _askPrice
    ) external returns (uint256 segmentId) {
        if (paused) revert MarketPaused();
        require(_windowDays > 0 && _windowDays <= 30, "Invalid window");
        require(_confidenceBps <= 10000, "Invalid confidence");
        require(_askPrice > 0, "Invalid price");

        segmentId = nextSegmentId++;

        segments[segmentId] = Segment({
            provider: msg.sender,
            segmentType: _type,
            windowDays: _windowDays,
            confidenceBps: _confidenceBps,
            active: true,
            askPrice: _askPrice,
            createdAt: block.timestamp
        });

        emit SegmentCreated(segmentId, msg.sender, _type, _askPrice);
    }

    /**
     * @dev Buy a segment with atomic settlement
     */
    function buySegment(uint256 segmentId) external nonReentrant {
        if (paused) revert MarketPaused();

        Segment storage segment = segments[segmentId];
        if (!segment.active) revert SegmentNotActive();
        if (accessRights[msg.sender][segmentId]) revert AlreadyHasAccess();

        uint256 askPrice = segment.askPrice;
        address provider = segment.provider;

        uint256 brokerSpread = (askPrice * brokerMarginBps) / 10000;
        uint256 providerPayout = askPrice - brokerSpread;

        if (patToken.allowance(msg.sender, address(this)) < askPrice) {
            revert InsufficientAllowance();
        }

        // ============ ATOMIC SETTLEMENT ============
        require(
            patToken.transferFrom(msg.sender, address(this), askPrice),
            "Transfer from consumer failed"
        );

        _recordPayout(provider, providerPayout, segmentId);

        require(
            patToken.transfer(brokerWallet, brokerSpread),
            "Transfer to broker failed"
        );

        accessRights[msg.sender][segmentId] = true;
        // ============ END ATOMIC SETTLEMENT ============

        emit SegmentPurchased(
            segmentId,
            msg.sender,
            provider,
            askPrice,
            providerPayout,
            brokerSpread
        );
    }

    function hasAccess(address consumer, uint256 segmentId) external view returns (bool) {
        return accessRights[consumer][segmentId];
    }

    function getSegment(uint256 segmentId) external view returns (
        SegmentType segmentType,
        uint8 windowDays,
        uint16 confidenceBps,
        uint256 askPrice,
        address provider,
        bool active,
        uint256 createdAt
    ) {
        Segment storage s = segments[segmentId];
        return (s.segmentType, s.windowDays, s.confidenceBps, s.askPrice, s.provider, s.active, s.createdAt);
    }

    function calculateSplit(uint256 askPrice) external view returns (
        uint256 providerPayout,
        uint256 brokerSpread
    ) {
        brokerSpread = (askPrice * brokerMarginBps) / 10000;
        providerPayout = askPrice - brokerSpread;
    }

    // ============ Provider Functions ============

    function deactivateSegment(uint256 segmentId) external {
        require(segments[segmentId].provider == msg.sender, "Not provider");
        segments[segmentId].active = false;
    }

    function updateSegmentPrice(uint256 segmentId, uint256 newAskPrice) external {
        require(segments[segmentId].provider == msg.sender, "Not provider");
        require(newAskPrice > 0, "Invalid price");
        segments[segmentId].askPrice = newAskPrice;
    }

    // ============ User Earnings & Withdrawal ============

    function _recordPayout(address user, uint256 amount, uint256 segmentId) internal {
        userEarnings[user] += amount;
        emit PayoutRecorded(user, amount, segmentId, block.timestamp);
    }

    function withdrawEarnings(uint256 amount) external nonReentrant {
        if (userEarnings[msg.sender] < amount) revert InsufficientEarnings();
        userEarnings[msg.sender] -= amount;
        require(patToken.transfer(msg.sender, amount), "Withdrawal transfer failed");
        emit Withdrawal(msg.sender, amount, block.timestamp);
    }

    function withdrawAllEarnings() external nonReentrant {
        uint256 amount = userEarnings[msg.sender];
        if (amount == 0) revert InsufficientEarnings();
        userEarnings[msg.sender] = 0;
        require(patToken.transfer(msg.sender, amount), "Withdrawal transfer failed");
        emit Withdrawal(msg.sender, amount, block.timestamp);
    }

    function getEarnings(address user) external view returns (uint256) {
        return userEarnings[user];
    }

    // ============ Admin Functions (for parameter updates between upgrades) ============

    function setBrokerMargin(uint256 newMarginBps) external onlyOwner {
        if (newMarginBps > 5000) revert InvalidConfiguration();
        brokerMarginBps = newMarginBps;
        emit ConfigUpdated(KEY_BROKER_MARGIN, newMarginBps);
    }

    function setBrokerWallet(address newWallet) external onlyOwner {
        require(newWallet != address(0), "Invalid address");
        brokerWallet = newWallet;
        emit WalletUpdated(KEY_BROKER_WALLET, newWallet);
    }

    function advancePhase() external onlyOwner {
        require(currentPhase != Phase.SPECULATION, "Already at final phase");
        currentPhase = Phase(uint8(currentPhase) + 1);
        emit PhaseAdvanced(uint8(currentPhase));
    }

    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
        emit MarketPaused(_paused);
    }

    // ============ View Functions ============

    function getPhaseString() external view returns (string memory) {
        if (currentPhase == Phase.UTILITY) return "UTILITY";
        if (currentPhase == Phase.FORWARDS) return "FORWARDS";
        if (currentPhase == Phase.SYNTHETICS) return "SYNTHETICS";
        return "SPECULATION";
    }

    function totalSegments() external view returns (uint256) {
        return nextSegmentId;
    }

    function getImplementation() external view returns (address) {
        return _getImplementation();
    }
}
