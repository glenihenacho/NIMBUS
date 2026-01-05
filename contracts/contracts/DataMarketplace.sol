// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title DataMarketplace
 * @dev Atomic settlement marketplace for PAT intent signal segments
 *
 * Core mechanism: Single transaction splits payment to all parties
 * - Browser Users receive BID (provider payout)
 * - Broker receives Spread (platform revenue)
 * - Consumer receives data access rights
 *
 * No inventory holding. Zero capital requirements. Instant settlement.
 *
 * Jurisdiction: Wyoming DAO LLC
 */
contract DataMarketplace is Ownable, ReentrancyGuard {
    // PAT token contract
    IERC20 public immutable patToken;

    // Market phases (1-4)
    enum Phase { UTILITY, FORWARDS, SYNTHETICS, SPECULATION }
    Phase public currentPhase;

    // Global configuration
    uint256 public brokerMarginBps;     // Basis points (e.g., 3000 = 30%)
    address public brokerWallet;         // Broker revenue recipient
    address public usersPoolWallet;      // Provider payout pool

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

    // Segment data (minimal storage)
    struct Segment {
        SegmentType segmentType;
        uint256 windowDays;          // Time window in days (e.g., 7)
        uint256 confidenceBps;       // Confidence score in bps (e.g., 7500 = 75%)
        uint256 askPrice;            // ASK price in PAT (wei)
        address provider;            // Original data provider
        bool active;                 // Segment available for purchase
        uint256 createdAt;           // Timestamp
    }

    // Segment registry
    mapping(uint256 => Segment) public segments;
    uint256 public nextSegmentId;

    // Access rights: consumer => segmentId => hasAccess
    mapping(address => mapping(uint256 => bool)) public accessRights;

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

    event ConfigUpdated(string indexed paramKey, uint256 value);
    event WalletUpdated(string indexed paramKey, address wallet);
    event PhaseAdvanced(uint8 newPhase);
    event MarketPaused(bool paused);
    event BrokerContractUpdated(string indexed paramKey);

    // Errors
    error MarketPaused();
    error SegmentNotActive();
    error AlreadyHasAccess();
    error InsufficientAllowance();
    error InvalidConfiguration();
    error PhaseNotAllowed();

    constructor(
        address _patToken,
        address _brokerWallet,
        address _usersPoolWallet,
        uint256 _brokerMarginBps
    ) Ownable(msg.sender) {
        require(_patToken != address(0), "Invalid PAT token");
        require(_brokerWallet != address(0), "Invalid broker wallet");
        require(_usersPoolWallet != address(0), "Invalid users pool");
        require(_brokerMarginBps <= 5000, "Margin too high"); // Max 50%

        patToken = IERC20(_patToken);
        brokerWallet = _brokerWallet;
        usersPoolWallet = _usersPoolWallet;
        brokerMarginBps = _brokerMarginBps;
        currentPhase = Phase.UTILITY;
    }

    // ============ Core Functions ============

    /**
     * @dev Create a new segment listing
     * @param _type Segment type (intent category)
     * @param _windowDays Time window in days
     * @param _confidenceBps Confidence score in basis points
     * @param _askPrice ASK price in PAT tokens (wei)
     */
    function createSegment(
        SegmentType _type,
        uint256 _windowDays,
        uint256 _confidenceBps,
        uint256 _askPrice
    ) external returns (uint256 segmentId) {
        if (paused) revert MarketPaused();
        require(_windowDays > 0 && _windowDays <= 30, "Invalid window");
        require(_confidenceBps <= 10000, "Invalid confidence");
        require(_askPrice > 0, "Invalid price");

        segmentId = nextSegmentId++;

        segments[segmentId] = Segment({
            segmentType: _type,
            windowDays: _windowDays,
            confidenceBps: _confidenceBps,
            askPrice: _askPrice,
            provider: msg.sender,
            active: true,
            createdAt: block.timestamp
        });

        emit SegmentCreated(segmentId, msg.sender, _type, _askPrice);
    }

    /**
     * @dev Buy a segment with atomic settlement
     * Single transaction splits payment to provider + broker + grants access
     * @param segmentId The segment to purchase
     */
    function buySegment(uint256 segmentId) external nonReentrant {
        if (paused) revert MarketPaused();

        Segment storage segment = segments[segmentId];
        if (!segment.active) revert SegmentNotActive();
        if (accessRights[msg.sender][segmentId]) revert AlreadyHasAccess();

        uint256 askPrice = segment.askPrice;
        address provider = segment.provider;

        // Calculate atomic split
        uint256 brokerSpread = (askPrice * brokerMarginBps) / 10000;
        uint256 providerPayout = askPrice - brokerSpread;

        // Verify consumer has approved enough PAT
        if (patToken.allowance(msg.sender, address(this)) < askPrice) {
            revert InsufficientAllowance();
        }

        // ============ ATOMIC SETTLEMENT ============
        // All three transfers happen in one transaction
        // If any fails, entire transaction reverts

        // 1. Consumer pays ASK to this contract (temporary)
        require(
            patToken.transferFrom(msg.sender, address(this), askPrice),
            "Transfer from consumer failed"
        );

        // 2. Provider receives BID (payout)
        require(
            patToken.transfer(provider, providerPayout),
            "Transfer to provider failed"
        );

        // 3. Broker receives spread
        require(
            patToken.transfer(brokerWallet, brokerSpread),
            "Transfer to broker failed"
        );

        // 4. Consumer receives access rights
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

    /**
     * @dev Check if consumer has access to a segment
     */
    function hasAccess(address consumer, uint256 segmentId) external view returns (bool) {
        return accessRights[consumer][segmentId];
    }

    /**
     * @dev Get segment details
     */
    function getSegment(uint256 segmentId) external view returns (
        SegmentType segmentType,
        uint256 windowDays,
        uint256 confidenceBps,
        uint256 askPrice,
        address provider,
        bool active,
        uint256 createdAt
    ) {
        Segment storage s = segments[segmentId];
        return (
            s.segmentType,
            s.windowDays,
            s.confidenceBps,
            s.askPrice,
            s.provider,
            s.active,
            s.createdAt
        );
    }

    /**
     * @dev Calculate payout split for a given ASK price
     */
    function calculateSplit(uint256 askPrice) external view returns (
        uint256 providerPayout,
        uint256 brokerSpread
    ) {
        brokerSpread = (askPrice * brokerMarginBps) / 10000;
        providerPayout = askPrice - brokerSpread;
    }

    // ============ Provider Functions ============

    /**
     * @dev Deactivate a segment (provider only)
     */
    function deactivateSegment(uint256 segmentId) external {
        require(segments[segmentId].provider == msg.sender, "Not provider");
        segments[segmentId].active = false;
    }

    /**
     * @dev Update segment ASK price (provider only)
     */
    function updateSegmentPrice(uint256 segmentId, uint256 newAskPrice) external {
        require(segments[segmentId].provider == msg.sender, "Not provider");
        require(newAskPrice > 0, "Invalid price");
        segments[segmentId].askPrice = newAskPrice;
    }

    // ============ Governance Function (Owner Only) ============

    /**
     * @dev Unified governance function to update broker contract parameters
     * Matches HANDOFF spec: updateBrokerContract(paramKey, paramValue)
     *
     * Supported paramKeys:
     *   - "brokerMargin": uint256 in basis points (max 5000 = 50%)
     *   - "brokerWallet": address for broker revenue
     *   - "usersPoolWallet": address for provider payouts
     *   - "phase": uint8 to advance phase (1→2→3→4)
     *   - "paused": bool for emergency pause
     *
     * @param paramKey The parameter to update
     * @param paramValue ABI-encoded value for the parameter
     */
    function updateBrokerContract(
        string calldata paramKey,
        bytes calldata paramValue
    ) external onlyOwner {
        bytes32 keyHash = keccak256(bytes(paramKey));

        if (keyHash == keccak256("brokerMargin")) {
            uint256 newMarginBps = abi.decode(paramValue, (uint256));
            if (newMarginBps > 5000) revert InvalidConfiguration();
            brokerMarginBps = newMarginBps;
            emit ConfigUpdated(paramKey, newMarginBps);

        } else if (keyHash == keccak256("brokerWallet")) {
            address newWallet = abi.decode(paramValue, (address));
            require(newWallet != address(0), "Invalid address");
            brokerWallet = newWallet;
            emit WalletUpdated(paramKey, newWallet);

        } else if (keyHash == keccak256("usersPoolWallet")) {
            address newWallet = abi.decode(paramValue, (address));
            require(newWallet != address(0), "Invalid address");
            usersPoolWallet = newWallet;
            emit WalletUpdated(paramKey, newWallet);

        } else if (keyHash == keccak256("phase")) {
            uint8 newPhase = abi.decode(paramValue, (uint8));
            require(newPhase > uint8(currentPhase), "Can only advance phase");
            require(newPhase <= uint8(Phase.SPECULATION), "Invalid phase");
            currentPhase = Phase(newPhase);
            emit PhaseAdvanced(newPhase);

        } else if (keyHash == keccak256("paused")) {
            bool newPaused = abi.decode(paramValue, (bool));
            paused = newPaused;
            emit MarketPaused(newPaused);

        } else {
            revert InvalidConfiguration();
        }

        emit BrokerContractUpdated(paramKey);
    }

    // ============ View Functions ============

    /**
     * @dev Get current market phase as string
     */
    function getPhaseString() external view returns (string memory) {
        if (currentPhase == Phase.UTILITY) return "UTILITY";
        if (currentPhase == Phase.FORWARDS) return "FORWARDS";
        if (currentPhase == Phase.SYNTHETICS) return "SYNTHETICS";
        return "SPECULATION";
    }

    /**
     * @dev Get total segments created
     */
    function totalSegments() external view returns (uint256) {
        return nextSegmentId;
    }
}
